"""Prepare isolated versions, run paired experiments, and publish saved evidence."""

import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import venv

from benchmark.common import ROOT, redact_secrets, save_json, source_hashes
from benchmark.suite import make_suite


MARKER = "BENCHMARK_RESULT="


def harness_hashes(directory):
    directory = Path(directory)
    paths = [path for path in directory.rglob("*.py") if "results" not in path.relative_to(directory).parts]
    if (directory / "requirements.txt").is_file():
        paths.append(directory / "requirements.txt")
    return {path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)}


def verify_harness(current, prepared, expected):
    if harness_hashes(prepared) != expected or harness_hashes(current) != expected:
        raise ValueError("Prepared or current harness changed; create a new experiment")


def dependency_lock(python):
    frozen = subprocess.check_output([str(python), "-m", "pip", "freeze", "--all"], text=True)
    return "\n".join(line for line in frozen.splitlines()
                     if not line.startswith(("-e ", "#", "defeatbeta-api"))) + "\n"


def export_source(ref, destination):
    if ref.startswith("-"):
        raise ValueError("Invalid source ref")
    commit = subprocess.check_output(["git", "rev-parse", "--verify", ref + "^{commit}"],
                                     cwd=ROOT, text=True).strip()
    data = subprocess.check_output(["git", "archive", commit, "defeatbeta_api", "pyproject.toml",
                                    "requirements.txt", "README.md"], cwd=ROOT)
    destination.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall(destination, filter="data")
    return commit


def prepare(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    harness = output / "harness" / "benchmark"
    harness.mkdir(parents=True)
    for path in (ROOT / "benchmark").rglob("*.py"):
        if "results" in path.parts:
            continue
        target = harness / path.relative_to(ROOT / "benchmark")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    shutil.copyfile(ROOT / "benchmark" / "requirements.txt", harness / "requirements.txt")
    harness_lock = dependency_lock(sys.executable)
    (output / "harness-dependencies.lock").write_text(harness_lock, encoding="utf-8")
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "environments": {},
                "harness_dependency_lock": harness_lock,
                "harness": harness_hashes(harness)}
    for name, ref in (("baseline", args.baseline), ("candidate", args.candidate)):
        source = output / name / "source"
        commit = export_source(ref, source)
        envdir = output / name / "venv"
        print(f"Preparing {name}: {commit}", flush=True)
        venv.EnvBuilder(with_pip=True).create(envdir)
        python = envdir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        install = [str(python), "-m", "pip", "install", "--disable-pip-version-check"]
        lock_input = getattr(args, name + "_lock", None)
        if lock_input is not None:
            install.extend(("-r", str(lock_input.resolve())))
        install.extend(("-e", str(source)))
        with (output / name / "install.log").open("w") as log:
            subprocess.run(install, stdout=log, stderr=log, check=True)
        lock = dependency_lock(python)
        (output / name / "dependencies.lock").write_text(lock, encoding="utf-8")
        environment = worker_environment(output, source)
        info = json.loads(subprocess.check_output([str(python), "-c",
            "import json; from benchmark.common import environment_info; print(json.dumps(environment_info()))"],
            cwd=source, env=environment, text=True))
        manifest["environments"][name] = {"commit": commit, "ref": ref, "source": str(source),
            "python": str(python), "source_hashes": source_hashes(source), "environment": info,
            "dependency_lock": lock}
        save_json(output / "experiment.json", manifest)
    return output


def worker_environment(experiment, source, server=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(experiment) / "harness")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if server:
        for key in list(env):
            if key.lower().endswith("_proxy"):
                env.pop(key)
        env["NO_PROXY"] = "localhost,127.0.0.1"
        env["SSL_CERT_FILE"] = server["certificate"]
        env["REQUESTS_CA_BUNDLE"] = server["certificate"]
    return env


def execute(experiment, environment, case, directory, timeout, server=None, action="measure"):
    payload = {"case": case, "cache_directory": str(directory), "action": action,
               "source": environment["source"], "source_hashes": environment["source_hashes"],
               "dependencies": environment["environment"]["dependencies"],
               "endpoint": server["url"] if server else None}
    started = time.perf_counter()
    try:
        result = subprocess.run([environment["python"], "-m", "benchmark.worker"],
            cwd=environment["source"], env=worker_environment(experiment, environment["source"], server),
            input=json.dumps(payload), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "timeout_seconds": timeout,
                "worker_wall_seconds": time.perf_counter() - started}
    matches = [line[len(MARKER):] for line in result.stdout.splitlines() if line.startswith(MARKER)]
    if len(matches) != 1:
        return {"status": "error", "returncode": result.returncode,
                "output": redact_secrets(result.stdout + result.stderr)}
    value = json.loads(matches[0])
    value.update(worker_wall_seconds=time.perf_counter() - started, returncode=result.returncode,
                 stderr=redact_secrets(result.stderr),
                 stdout=redact_secrets("\n".join(line for line in result.stdout.splitlines()
                                                  if not line.startswith(MARKER))))
    if result.returncode:
        value["status"] = "error"
    return value


def paired_order(round_index, case_index):
    return ("baseline", "candidate") if (round_index + case_index) % 2 == 0 else ("candidate", "baseline")


def measure(args):
    from benchmark.fixture import generate, verify
    from benchmark.server import serve_fixture
    from benchmark.report import render

    experiment = args.experiment.resolve()
    manifest = json.loads((experiment / "experiment.json").read_text())
    harness = experiment / "harness" / "benchmark"
    verify_harness(ROOT / "benchmark", harness, manifest["harness"])
    if dependency_lock(sys.executable) != manifest["harness_dependency_lock"]:
        raise ValueError("Harness dependencies changed; create a new experiment")
    for environment in manifest["environments"].values():
        if dependency_lock(environment["python"]) != environment["dependency_lock"]:
            raise ValueError("Prepared dependencies changed; create a new experiment")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    destination = experiment / f"{stamp}_{args.mode}_{args.protocol}_{args.suite}"
    destination.mkdir()
    record = {"schema_version": 1, "stage": "development", "status": "running", "created_at": stamp,
              "workflow": {"repository": os.environ.get("GITHUB_REPOSITORY"),
                           "run_id": os.environ.get("GITHUB_RUN_ID"),
                           "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
                           "sha": os.environ.get("GITHUB_SHA")},
              "mode": args.mode, "protocol_control": args.protocol if args.mode == "controlled" else None,
              "network": args.network_label, "experiment": manifest, "rounds": args.rounds,
              "suite": make_suite(args.suite), "records": [], "preparation": [],
              "policy": {"data": "Latest remote data; daily changes accepted and recorded" if args.mode == "live"
                         else "One checksummed synthetic fixture for both products",
                         "cache": "Fresh per variant/case/round; disk-warm uses a separate seeding process",
                         "product": "Declared defaults except isolated cache directory and disabled DuckDB external file cache",
                         "metrics": "Fully materialized API; constructor reported separately and in first result",
                         "order": "Balanced alternating AB/BA; sequential versions on one host",
                         "stream": "Fixed total query plan; natural cache reuse inside a batch",
                         "scope": "Paired changes in this environment; no universal bandwidth claim"}}
    target = destination / "results.json"
    save_json(target, record)
    with tempfile.TemporaryDirectory(prefix="defeatbeta-benchmark-") as temporary:
        temporary = Path(temporary)
        if args.mode == "controlled":
            fixture = temporary / "fixture"
            generate(fixture)
            record["fixture"] = verify(fixture)
            context = serve_fixture(fixture, temporary, args.protocol)
        else:
            context = nullcontext(None)
        with context as server:
            unresolved = {}
            for case in record["suite"]["cases"]:
                for task in case["tasks"]:
                    if task["method"] in ("transcript_body", "news_body"):
                        unresolved[(task["symbol"], task["method"])] = task
            if unresolved:
                directory = temporary / "discovery"
                directory.mkdir()
                case = {"id": "discovery", "tasks": list(unresolved.values())}
                discovered = execute(experiment, manifest["environments"]["baseline"], case, directory,
                                     args.timeout, server, "discover")
                record["preparation"].append(discovered)
                if discovered["status"] != "ok":
                    record["status"] = "invalid_preparation"
                    save_json(target, record)
                    render(target)
                    return 1
                lookup = {(task["symbol"], task["method"]): task for task in discovered["tasks"]}
                for case in record["suite"]["cases"]:
                    case["tasks"] = [lookup.get((task["symbol"], task["method"]), task) for task in case["tasks"]]
                record["coverage"] = discovered["coverage"]
            record["resolved_suite_sha256"] = hashlib.sha256(json.dumps(record["suite"], sort_keys=True).encode()).hexdigest()
            save_json(target, record)
            for round_index in range(args.rounds):
                for case_index, case in enumerate(record["suite"]["cases"]):
                    for variant in paired_order(round_index, case_index):
                        print(f"round={round_index + 1}/{args.rounds} case={case['id']} variant={variant}", flush=True)
                        directory = temporary / f"cache-{round_index}-{case_index}-{variant}"
                        directory.mkdir()
                        env = manifest["environments"][variant]
                        if case["state"] == "disk_warm":
                            seed = {**case, "state": "first_use"}
                            outcome = execute(experiment, env, seed, directory, args.timeout, server)
                            record["preparation"].append({"case": case["id"], "round": round_index + 1,
                                                         "variant": variant, "measurement": outcome})
                            if outcome["status"] != "ok":
                                record["records"].append({"case": case["id"], "round": round_index + 1,
                                                          "variant": variant, "measurement": outcome})
                                save_json(target, record)
                                continue
                        server_before = server["status"]() if server else None
                        value = execute(experiment, env, case, directory, args.timeout, server)
                        server_after = server["status"]() if server else None
                        record["records"].append({"case": case["id"], "round": round_index + 1,
                                                  "variant": variant, "measurement": value,
                                                  "server_before": server_before, "server_after": server_after})
                        save_json(target, record)
                        # Each case is complete, so no cache or prefetch can leak into the next case.
                        shutil.rmtree(directory)
                        print(f"  {value['status']} api_seconds={value.get('wall_seconds')}", flush=True)
            record["status"] = "complete"
            save_json(target, record)
            summary = render(target)
            print(f"Report: {target.with_suffix('.md')}", flush=True)
            return 0 if summary["valid"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare", help="Install two explicit source revisions into isolated environments")
    compare_parser = commands.add_parser("compare", help="Prepare and run a paired experiment")
    for command in (prepare_parser, compare_parser):
        command.add_argument("--baseline", required=True)
        command.add_argument("--candidate", default="HEAD")
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--baseline-lock", type=Path, help="Reuse the archived baseline dependency lock")
        command.add_argument("--candidate-lock", type=Path, help="Reuse the archived candidate dependency lock")
    run_parser = commands.add_parser("run", help="Run an already prepared experiment; keep every attempt")
    run_parser.add_argument("--experiment", type=Path, required=True)
    for command in (run_parser, compare_parser):
        command.add_argument("--mode", choices=("controlled", "live"), default="controlled")
        command.add_argument("--suite", choices=("smoke", "release"), default="release")
        command.add_argument("--rounds", type=int, default=6)
        command.add_argument("--protocol", choices=("h2", "http1"), default="h2")
        command.add_argument("--network-label", default="Unspecified local network")
        command.add_argument("--timeout", type=float, default=180)
    report_parser = commands.add_parser("report", help="Render a report from saved JSON without making requests")
    report_parser.add_argument("record", type=Path)
    final_parser = commands.add_parser("finalize", help="Validate and package one complete workflow run for a release")
    final_parser.add_argument("--source", type=Path, required=True)
    final_parser.add_argument("--output", type=Path, required=True)
    final_parser.add_argument("--release", required=True)
    final_parser.add_argument("--candidate-commit", required=True)
    final_parser.add_argument("--workflow-run", type=Path, required=True)
    args = parser.parse_args()
    if getattr(args, "rounds", 1) < 1 or not 0 < getattr(args, "timeout", 1) < float("inf"):
        parser.error("Rounds and timeout must be positive and finite")
    if args.command == "prepare":
        prepare(args)
        return 0
    if args.command == "compare":
        args.experiment = prepare(args)
        return measure(args)
    if args.command == "run":
        return measure(args)
    if args.command == "finalize":
        from benchmark.publication import finalize, package
        directory = finalize(args.source, args.output, args.release, args.candidate_commit,
                             json.loads(args.workflow_run.read_text()))
        print(package(directory))
        return 0
    from benchmark.report import render
    return 0 if render(args.record)["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
