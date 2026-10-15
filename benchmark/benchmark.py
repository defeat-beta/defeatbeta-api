"""Prepare isolated versions, run paired experiments, and publish saved evidence."""

import argparse
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
import time
import venv

from benchmark.common import ROOT, redact_secrets, save_json, source_hashes
from benchmark.e2e import plan


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
        if not ref:
            continue
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
        environment = worker_environment(output)
        info = json.loads(subprocess.check_output([str(python), "-c",
            "import json; from benchmark.common import environment_info; print(json.dumps(environment_info()))"],
            cwd=source, env=environment, text=True))
        manifest["environments"][name] = {"commit": commit, "ref": ref, "source": str(source),
            "python": str(python), "source_hashes": source_hashes(source), "environment": info,
            "dependency_lock": lock}
        save_json(output / "experiment.json", manifest)
    return output


def worker_environment(experiment):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(experiment) / "harness")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def execute(experiment, environment, request, directory, timeout):
    directory.mkdir(parents=True, exist_ok=False)
    payload = {**request, "cache_directory": str(directory / "cache"),
               "source": environment["source"], "source_hashes": environment["source_hashes"],
               "dependencies": environment["environment"]["dependencies"],
               "progress_path": str(directory / "progress.jsonl")}

    def partial(value):
        if "completed_tasks" not in value and Path(payload["progress_path"]).is_file():
            rows = []
            for line in Path(payload["progress_path"]).read_text().splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    break
            value.update(completed_tasks=len(rows), results=rows)
        return value
    started = time.perf_counter()
    try:
        result = subprocess.run([environment["python"], "-m", "benchmark.worker"],
            cwd=environment["source"], env=worker_environment(experiment),
            input=json.dumps(payload), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return partial({"status": "timeout", "worker_wall_seconds": time.perf_counter() - started})
    matches = [line[len(MARKER):] for line in result.stdout.splitlines() if line.startswith(MARKER)]
    if len(matches) != 1:
        return partial({"status": "worker_error", "returncode": result.returncode,
                        "output": redact_secrets(result.stdout + result.stderr)})
    try:
        value = json.loads(matches[0])
    except json.JSONDecodeError:
        return partial({"status": "worker_error", "error": "Worker produced invalid JSON"})
    value.update(worker_wall_seconds=time.perf_counter() - started, returncode=result.returncode)
    if result.returncode and value.get("status") == "complete":
        value["status"] = "worker_error"
    return partial(value)


def paired_order(round_index, phase_index):
    return ("baseline", "candidate") if (round_index + phase_index) % 2 == 0 else ("candidate", "baseline")


def measure(args):
    from benchmark.report import render

    experiment = args.experiment.resolve()
    manifest = json.loads((experiment / "experiment.json").read_text())
    verify_harness(ROOT / "benchmark", experiment / "harness" / "benchmark", manifest["harness"])
    if dependency_lock(sys.executable) != manifest["harness_dependency_lock"]:
        raise ValueError("Harness dependencies changed; create a new experiment")
    for environment in manifest["environments"].values():
        if dependency_lock(environment["python"]) != environment["dependency_lock"]:
            raise ValueError("Prepared dependencies changed; create a new experiment")
    destination = experiment / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    destination.mkdir()
    workload = json.loads(args.plan.read_text())
    plan.validate_plan(workload)
    selected = [phase for phase in plan.phases() if not args.phase or phase["id"] == args.phase]
    record = {"schema_version": 2, "stage": "development", "status": "running",
              "workflow": {key: os.environ.get(value) for key, value in (
                  ("repository", "GITHUB_REPOSITORY"), ("run_id", "GITHUB_RUN_ID"),
                  ("run_attempt", "GITHUB_RUN_ATTEMPT"), ("sha", "GITHUB_SHA"))},
              "experiment": manifest, "rounds": args.rounds, "plan": workload,
              "phases": selected, "records": []}
    target = destination / "results.json"
    save_json(target, record)
    for number in range(args.rounds):
        for phase in selected:
            index = plan.phases().index(phase)
            for variant in paired_order(number, index):
                if variant not in manifest["environments"]:
                    continue
                print(f"round={number + 1} phase={phase['id']} variant={variant}", flush=True)
                directory = destination / f"cache-{number}-{index}-{variant}"
                value = execute(experiment, manifest["environments"][variant],
                    {"action": "measure", "phase": phase, "plan": workload}, directory, args.timeout)
                record["records"].append({"phase": phase["id"], "round": number + 1,
                                          "variant": variant, "measurement": value})
                save_json(target, record)
                shutil.rmtree(directory / "cache", ignore_errors=True)
    record["status"] = "complete"
    save_json(target, record)
    return 0 if render(target)["valid"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "compare", "discover"):
        command = commands.add_parser(name)
        command.add_argument("--baseline", help="Optional comparison ref; omit for the first standalone report")
        command.add_argument("--candidate", default="HEAD")
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--baseline-lock", type=Path)
        command.add_argument("--candidate-lock", type=Path)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--experiment", type=Path, required=True)
    for command in (commands.choices["compare"], run_parser):
        command.add_argument("--plan", type=Path, required=True)
        command.add_argument("--phase", choices=[phase["id"] for phase in plan.phases()])
        command.add_argument("--rounds", type=int, default=1)
        command.add_argument("--timeout", type=float, default=18000)
    report_parser = commands.add_parser("report")
    report_parser.add_argument("record", type=Path)
    collect_parser = commands.add_parser("collect")
    collect_parser.add_argument("--source", type=Path, required=True)
    collect_parser.add_argument("--output", type=Path, required=True)
    final_parser = commands.add_parser("finalize")
    for option in ("source", "output", "workflow-run"):
        final_parser.add_argument("--" + option, type=Path, required=True)
    final_parser.add_argument("--release", required=True)
    final_parser.add_argument("--candidate-commit", required=True)
    args = parser.parse_args()
    if (getattr(args, "rounds", 1) < 1
            or not 0 < getattr(args, "timeout", 1) < float("inf")):
        parser.error("Rounds and timeout must be positive and finite")
    if args.command in ("prepare", "compare", "discover"):
        args.experiment = prepare(args)
        if args.command == "prepare":
            return 0
        if args.command == "discover":
            manifest = json.loads((args.experiment / "experiment.json").read_text())
            value = execute(args.experiment, manifest["environments"]["candidate"],
                            {"action": "discover"}, args.experiment / "discovery", 1800)
            save_json(args.experiment / "discovery.json", value)
            if value["status"] != "complete":
                return 1
            save_json(args.experiment / "plan.json", value["plan"])
            return 0
    if args.command in ("compare", "run"):
        return measure(args)
    if args.command == "collect":
        from benchmark.report import collect, render
        target = collect(args.source, args.output)
        return 0 if render(target)["valid"] else 1
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
