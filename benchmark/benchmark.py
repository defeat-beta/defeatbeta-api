"""Prepare isolated product versions and run benchmark workers inside them."""

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
               "progress_path": str(directory / "progress.jsonl"),
               "time_budget_seconds": timeout * .95}

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
