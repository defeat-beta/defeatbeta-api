"""Reproducible cold stock-price benchmark; run --help for usage."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import statistics
import subprocess
import sys
import tempfile
import time
import uuid

from config import (
    BASELINE_SETTINGS, DEFAULT_REVISION, DEFAULT_RUNS, DEFAULT_SYMBOL,
    DEFAULT_TIMEOUT, stock_prices_url, validate_symbol,
)
from queries import fixed_query

ROOT = Path(__file__).resolve().parent


def summarize(samples):
    values = [sample["e2e_seconds"] for sample in samples if sample["status"] == "ok"]
    if not values:
        return None
    return {
        "count": len(values), "median_seconds": statistics.median(values),
        "min_seconds": min(values), "max_seconds": max(values),
        "std_seconds": statistics.stdev(values) if len(values) > 1 else None,
    }


def run_worker(payload, timeout, worker_path=None):
    payload = dict(payload)
    payload["launch_ns"] = time.perf_counter_ns()
    try:
        completed = subprocess.run(
            [sys.executable, str(worker_path or ROOT / "queries.py")],
            input=json.dumps(payload), text=True, capture_output=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        def decode(value):
            return value.decode(errors="replace") if isinstance(value, bytes) else value
        return {
            "status": "timeout", "timeout_seconds": timeout,
            "stdout": decode(exc.stdout), "stderr": decode(exc.stderr),
        }
    lines = completed.stdout.splitlines()
    messages = [line[len("BENCH_RESULT="):] for line in lines if line.startswith("BENCH_RESULT=")]
    try:
        if len(messages) != 1:
            raise ValueError("worker did not return exactly one result")
        sample = json.loads(messages[0])
        if completed.returncode and sample.get("status") != "error":
            raise ValueError("worker exited unsuccessfully")
        if sample.get("status") not in ("ok", "empty_result", "error"):
            raise ValueError("worker returned an unknown status")
    except (ValueError, TypeError) as exc:
        sample = {"status": "error", "error": str(exc)}
    sample.update({
        "returncode": completed.returncode, "stdout": completed.stdout,
        "stderr": completed.stderr,
        "worker_wall_seconds": (time.perf_counter_ns() - payload["launch_ns"]) / 1e9,
    })
    return sample


def check_consistency(samples):
    good = [sample for sample in samples if sample["status"] == "ok"]
    if len({json.dumps(sample["result"], sort_keys=True) for sample in good}) > 1:
        for sample in good:
            sample["status"] = "result_mismatch"


def preflight():
    import duckdb
    import pandas
    import psutil

    connection = duckdb.connect(":memory:")
    extensions = connection.execute(
        "SELECT extension_name, installed, extension_version, install_path "
        "FROM duckdb_extensions() WHERE extension_name IN ('httpfs', 'cache_httpfs') ORDER BY 1"
    ).fetchall()
    connection.close()
    if len(extensions) != 2 or not all(row[1] for row in extensions):
        raise RuntimeError("Install httpfs and cache_httpfs before benchmarking; installation is not timed")
    memory_gb = int(psutil.virtual_memory().total * 0.8 / (1024 ** 3))
    if memory_gb < 1:
        raise RuntimeError("Baseline memory limit resolves to less than 1 GB")
    manifest = []
    for name, installed, version, path in extensions:
        manifest.append({
            "name": name, "version": version, "path": path,
            "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        })
    environment = {
        "python": sys.version, "executable": sys.executable,
        "duckdb": duckdb.__version__, "pandas": pandas.__version__,
        "platform": platform.platform(), "machine": platform.machine(),
        "logical_cpus": os.cpu_count(), "physical_cpus": psutil.cpu_count(logical=False),
        "memory_bytes": psutil.virtual_memory().total,
        "extensions": manifest,
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("config.py", "queries.py", "bench.py")
        },
        "proxy_environment_variables_present": sorted(
            key for key in os.environ if key.lower() in ("http_proxy", "https_proxy", "all_proxy", "no_proxy")
        ),
    }
    return environment, {**BASELINE_SETTINGS, "memory_limit": f"{memory_gb}GB"}


def write_run(path, report):
    # Preserve full machine-readable evidence inside the requested Markdown artifact.
    stats = report["statistics"]
    lines = [f"# {report['run_id']}", "", f"Status: {report['status']}", ""]
    if stats:
        lines += [f"Median cold query: {stats['median_seconds']:.6f} s", ""]
    lines += [
        "| Trial | Status | End to end (s) | Initialization (s) | Query (s) | Rows |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for sample in report["samples"]:
        values = [f"{sample[key]:.6f}" if key in sample else "—" for key in
                  ("e2e_seconds", "initialization_seconds", "query_seconds")]
        lines.append(f"| {sample['trial']} | {sample['status']} | {' | '.join(values)} | "
                     f"{sample.get('result', {}).get('rows', '—')} |")
    lines += ["", "## Raw report", "", "```json", json.dumps(report, indent=2), "```", ""]
    temporary = path.with_suffix(".tmp")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    temporary.replace(path)


def update_summary(output):
    lines = [
        "# Cold query benchmark runs", "",
        "Only complete, consistent runs have a comparison median. No cross-environment speedup is inferred.", "",
        "| Run | Symbol | Revision | Status | Valid / requested | Median (s) | Min (s) | Max (s) | Sample std (s) |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for path in sorted((output / "runs").glob("*.md")):
        body = path.read_text(encoding="utf-8")
        report = json.loads(body.split("```json\n", 1)[1].rsplit("\n```", 1)[0])
        stats = report["statistics"]
        cells = [f"{stats[key]:.6f}" if stats and stats[key] is not None else "—" for key in
                 ("median_seconds", "min_seconds", "max_seconds", "std_seconds")]
        symbol = report["symbol"].replace("|", "&#124;").replace("<", "&lt;")
        lines.append(
            f"| [{report['run_id']}](runs/{path.name}) | {symbol} | {report['revision'][:12]} | "
            f"{report['status']} | {sum(s['status'] == 'ok' for s in report['samples'])} / "
            f"{report['requested_runs']} | {' | '.join(cells)} |"
        )
    temporary = output / "summary.tmp"
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(output / "summary.md")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--tag", default="baseline")
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Per-worker wall timeout in seconds")
    parser.add_argument("--output", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    try:
        validate_symbol(args.symbol)
        url = stock_prices_url(args.revision)
        if args.runs < 1 or not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("runs and timeout must be positive and finite")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", args.tag):
            raise ValueError("tag must be 1-64 filename-safe characters")
    except ValueError as exc:
        parser.error(str(exc))
    preflight_start = time.perf_counter()
    environment, settings = preflight()
    preparation_seconds = time.perf_counter() - preflight_start
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run_id = f"{timestamp}_{args.tag}_{uuid.uuid4().hex[:8]}"
    output = args.output.resolve()
    (output / "runs").mkdir(parents=True, exist_ok=True)
    path = output / "runs" / f"{run_id}.md"
    report = {
        "format_version": 1, "run_id": run_id, "tag": args.tag, "status": "running",
        "revision": args.revision, "url": url, "symbol": args.symbol,
        "sql": fixed_query(url), "parameters": [args.symbol],
        "requested_runs": args.runs, "timeout_seconds": args.timeout,
        "preflight_seconds": preparation_seconds,
        "environment": environment, "configured_settings": settings,
        "methodology": {
            "cold": "Fresh process and unique empty cache_httpfs directory per trial; no query warmup",
            "main_metric": "Parent pre-spawn monotonic timestamp to worker DataFrame materialization",
            "excluded": "Preflight, extension installation, result hashing, report writing, teardown",
            "uncontrolled_caches": "OS code pages, DNS, proxy and remote CDN caches; not a machine-cold benchmark",
            "scope": "Fixed SQL with current client settings; excludes Ticker and spec.json validation",
            "std": "Sample standard deviation; undefined for one sample",
            "cache_bytes": "On-disk footprint after query; not measured network bytes",
            "comparison": "Require identical data, symbol, result hash, environment and extension binaries",
        },
        "samples": [], "statistics": None,
    }
    write_run(path, report)
    for trial in range(1, args.runs + 1):
        print(f"[{trial}/{args.runs}] {args.symbol}: starting isolated cold worker", flush=True)
        with tempfile.TemporaryDirectory(prefix="stock-price-cold-") as directory:
            cache = Path(directory) / "http-cache"
            cache.mkdir()
            sample = run_worker({
                "url": url, "symbol": args.symbol, "cache_directory": str(cache), "settings": settings,
            }, args.timeout)
            sample["trial"] = trial
            report["samples"].append(sample)
        check_consistency(report["samples"])
        write_run(path, report)
        print(f"[{trial}/{args.runs}] {sample['status']}: "
              f"{sample.get('e2e_seconds', 'unavailable')} s", flush=True)
    report["status"] = "complete" if all(s["status"] == "ok" for s in report["samples"]) else "invalid"
    report["statistics"] = summarize(report["samples"]) if report["status"] == "complete" else None
    write_run(path, report)
    update_summary(output)
    print(f"Report: {path}")
    if report["statistics"]:
        print(f"Median: {report['statistics']['median_seconds']:.6f} s")
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())
