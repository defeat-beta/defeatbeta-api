"""Bound one sampled end-to-end calibration before choosing release repetitions."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from benchmark.common import ROOT, environment_info, redact_secrets, save_json, source_hashes
from benchmark.e2e import plan


def worker(request_path, response_path):
    from benchmark.e2e.backend import ProductBackend, discover
    from benchmark.e2e.execution import measure_latency, measure_throughput
    import defeatbeta_api

    request = json.loads(Path(request_path).read_text())
    if (Path(defeatbeta_api.__file__).resolve().parent.parent != ROOT
            or source_hashes() != request["source_hashes"]):
        raise RuntimeError("Calibration source escaped the recorded checkout")
    backend = ProductBackend(request["cache_directory"], request.get("plan"))
    deadline = time.monotonic() + request["budget_seconds"]
    try:
        if request["action"] == "discover":
            result = {"status": "complete", "plan": discover(backend)}
        else:
            phase = request["phase"]
            if phase["kind"] == "latency":
                progress = Path(response_path).with_suffix(".jsonl")
                with progress.open("w", encoding="utf-8") as stream:
                    def emit(row):
                        stream.write(json.dumps(redact_secrets(row), ensure_ascii=True, allow_nan=False) + "\n")
                        stream.flush()
                    result = measure_latency(request["plan"], backend, phase["state"], emit=emit,
                                             stop=lambda: time.monotonic() >= deadline)
            else:
                result = measure_throughput(request["plan"], backend, phase["state"], phase["concurrency"],
                                               stop=lambda: time.monotonic() >= deadline)
            result["cache_settings"] = backend.settings()
            result["observed_dataset_version"] = backend.client._data_update_time
        save_json(response_path, result)
    except Exception as exc:
        save_json(response_path, {"status": "worker_error", "error_type": type(exc).__name__,
                                  "error": redact_secrets(str(exc))})
        return 1
    finally:
        backend.close()
    return 0


def run_worker(output, identifier, request, timeout):
    folder = output / identifier
    folder.mkdir()
    request_path, response_path = folder / "request.json", folder / "measurement.json"
    request["cache_directory"] = str(folder / "cache")
    request["budget_seconds"] = timeout
    save_json(request_path, request)
    started = time.perf_counter()
    try:
        with (folder / "console.log").open("w", encoding="utf-8") as log:
            completed = subprocess.run([sys.executable, "-m", "benchmark.e2e.calibrate", "--worker",
                                        str(request_path), str(response_path)],
                                       cwd=ROOT, stdout=log, stderr=log, timeout=timeout)
        result = json.loads(response_path.read_text()) if response_path.is_file() else {
            "status": "worker_error", "error": "Worker did not produce a measurement"}
        result["returncode"] = completed.returncode
    except subprocess.TimeoutExpired:
        progress = response_path.with_suffix(".jsonl")
        rows = []
        if progress.is_file():
            for line in progress.read_text().splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    break
        result = {"status": "budget_exhausted", "completed_tasks": len(rows), "results": rows}
        save_json(response_path, result)
    result["elapsed_seconds"] = time.perf_counter() - started
    result["evidence"] = response_path.relative_to(output).as_posix()
    progress = response_path.with_suffix(".jsonl")
    if "completed_tasks" not in result and progress.is_file():
        rows = []
        for line in progress.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                break
        result.update(completed_tasks=len(rows), results=rows)
    # Cache files are transient preparation, not calibration evidence.
    import shutil
    shutil.rmtree(folder / "cache", ignore_errors=True)
    return result


def render(record, output):
    lines = ["# Sampled end-to-end calibration", "", "Stage: **calibration; not a version comparison or release report**.", "",
             f"Source commit: `{record['commit']}`. Status: `{record['status']}`.",
             f"Wall-clock budget: {record['budget_seconds']} seconds; elapsed: {record['elapsed_seconds']:.1f} seconds.", "",
             "One candidate, one round. Timings plan the workload; they do not establish a release speedup."]
    workload = record.get("plan")
    if workload:
        lines += ["", f"Tickers ({len(workload['symbols'])}): " + ", ".join(workload["symbols"]) + ".",
                  f"Query operations: {len(workload['methods'])}; fixed tasks per phase: {workload['task_count']}.",
                  f"Workload identity: `{workload['sha256']}`.", "",
                  "Every throughput concurrency executes this identical Cartesian workload once.",
                  "Latency cold queries have isolated caches; cold throughput begins with one empty shared cache.",
                  "Cached measurements require no query-data cache misses after warming every task.",
                  "Ticker initialization, preparation, and result hashing are outside individual API timing.", ""]
    lines += ["", "| Phase | Status | Completed | Successful | Not applicable | Failed | Phase elapsed (s) | Batch/query wall (s) | API P95 (s) | Cache misses |",
              "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for entry in record["phases"]:
        value = entry["measurement"]
        elapsed = value.get("wall_seconds")
        p95 = value.get("latency", {}).get("p95_seconds")
        lines.append(f"| {entry['phase']['id']} | {value['status']} | {value.get('completed_tasks', 0)} | "
                     f"{value.get('successful_tasks', 0)} | {value.get('not_applicable_tasks', 0)} | "
                     f"{value.get('failed_tasks', 0)} | {value['elapsed_seconds']:.2f} | "
                     f"{f'{elapsed:.4f}' if elapsed is not None else 'n/a'} | "
                     f"{f'{p95:.4f}' if p95 is not None else 'n/a'} | {value.get('cache_misses', 'n/a')} |")
    if len(record["phases"]) == len(plan.phases()) and all(
            entry["measurement"]["status"] == "complete" for entry in record["phases"]):
        lines += ["", "All phases finished without query/cache errors. A rough paired-run planning estimate",
                  f"is {record['elapsed_seconds'] * 4 / 60:.1f} minutes for two rounds and "
                  f"{record['elapsed_seconds'] * 12 / 60:.1f} minutes for six rounds.",
                  "These estimates assume similar baseline/candidate costs and exclude dependency installation."]
    else:
        lines += ["", "Incomplete phases, warmup failures, or cache misses prevent a complete-matrix runtime claim.",
                  "Retain these observations and resolve the coverage/validity issues before choosing release rounds."]
    lines += ["", "## Query errors", ""]
    errors = []
    for entry in record["phases"]:
        measurement = entry["measurement"]
        for row in measurement.get("results", []) + measurement.get("warmup_errors", []):
            if row.get("status") == "error":
                errors.append({"phase": entry["phase"]["id"], **row})
    for row in errors[:50]:
        lines.append(f"- `{row['phase']}` / `{row['symbol']}` / `{row['method']}`: "
                     f"`{row.get('error_type')}`. See raw evidence for the complete error.")
    lines += [f"Total recorded query/warmup errors: {len(errors)}.", "",
              "Raw phase measurements preserve every outcome; missing work is not counted as complete.",
              "Application cache capacity is deliberately generous. This does not change product defaults.",
              "An all-local-cache claim is invalid if query-data fetches occur during the measured phase.", ""]
    content = "\n".join(lines)
    if any("\u4e00" <= char <= "\u9fff" for char in content):
        raise ValueError("Calibration report must be English")
    (output / "calibration.md").write_text(content, encoding="utf-8")


def calibrate(output, budget_seconds):
    if not 0 < budget_seconds < float("inf"):
        raise ValueError("Budget must be positive and finite")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all", "--",
                                      "defeatbeta_api", "benchmark"], cwd=ROOT, text=True)
    if dirty.strip():
        raise ValueError("Commit the product and harness before calibration")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    record = {"schema_version": 1, "stage": "calibration", "commit": commit,
              "status": "running", "budget_seconds": budget_seconds, "phases": [],
              "environment": environment_info(), "source_hashes": source_hashes(),
              "workflow": {key: os.environ.get(value) for key, value in (
                  ("repository", "GITHUB_REPOSITORY"), ("run_id", "GITHUB_RUN_ID"),
                  ("run_attempt", "GITHUB_RUN_ATTEMPT"), ("sha", "GITHUB_SHA"))}}
    save_json(output / "calibration.json", record)

    def checkpoint():
        record["elapsed_seconds"] = time.perf_counter() - started
        save_json(output / "calibration.json", record)
        render(record, output)

    request = {"source_hashes": record["source_hashes"], "action": "discover"}
    print("Preparing the fixed sample and complete query manifest", flush=True)
    discovery = run_worker(output, "discovery", request, max(0.001, budget_seconds))
    record["discovery"] = discovery
    if discovery["status"] != "complete":
        record["status"] = discovery["status"]
        checkpoint()
        return 2
    record["plan"] = discovery["plan"]
    save_json(output / "plan.json", record["plan"])
    checkpoint()
    for phase in plan.phases():
        remaining = budget_seconds - (time.perf_counter() - started)
        if remaining <= 0:
            record["status"] = "budget_exhausted"
            break
        print(f"Calibrating {phase['id']}: {record['plan']['task_count']} fixed tasks", flush=True)
        value = run_worker(output, phase["id"], {"source_hashes": record["source_hashes"],
            "action": "measure", "phase": phase, "plan": record["plan"]}, remaining)
        record["phases"].append({"phase": phase, "measurement": value})
        checkpoint()
        print(f"  {value['status']} elapsed={value['elapsed_seconds']:.1f}s "
              f"completed={value.get('completed_tasks', 0)}", flush=True)
        if value["status"] == "budget_exhausted":
            record["status"] = "budget_exhausted"
            break
    else:
        record["status"] = ("complete" if all(entry["measurement"]["status"] == "complete"
                                              for entry in record["phases"]) else "needs_review")
    checkpoint()
    return 0 if record["status"] in ("complete", "needs_review") else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--budget-seconds", type=float, default=1800)
    parser.add_argument("--worker", nargs=2, metavar=("REQUEST", "RESPONSE"))
    args = parser.parse_args()
    if args.worker:
        return worker(*args.worker)
    if args.output is None:
        parser.error("--output is required")
    return calibrate(args.output, args.budget_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
