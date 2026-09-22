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
    BASELINE_SETTINGS, DEFAULT_REVISION, DEFAULT_RUNS, DEFAULT_SYMBOLS,
    DEFAULT_TIMEOUT, stock_prices_url, validate_symbol,
)
from queries import fixed_query
from records import archive_record, prune_local, write_record
from reports import render_markdown

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
        "returncode": completed.returncode,
        "stdout": "\n".join(line for line in lines if not line.startswith("BENCH_RESULT=")),
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
            for name in ("config.py", "queries.py", "bench.py", "records.py")
        },
        "proxy_environment_variables_present": sorted(
            key for key in os.environ if key.lower() in ("http_proxy", "https_proxy", "all_proxy", "no_proxy")
        ),
    }
    return environment, {**BASELINE_SETTINGS, "memory_limit": f"{memory_gb}GB"}


def _latest_local_run(output: Path, tag: str) -> Path | None:
    """Find the most recent local run file for the given tag."""
    local_dir = output / "local"
    if not local_dir.exists():
        return None
    candidates = []
    for path in local_dir.glob("*.json"):
        if path.is_symlink():
            continue
        # Filename format: {timestamp}_{tag}_{uuid}.json
        if f"_{tag}_" in path.name:
            try:
                ts_str = path.name.split("_", 1)[0]
                dt = datetime.strptime(ts_str, "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=timezone.utc)
                candidates.append((dt, path))
            except ValueError:
                continue
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _next_archive_number(output: Path, tag: str) -> int:
    """Find the next archive sequence number for the given tag."""
    archive_dir = output / "archive"
    if not archive_dir.exists():
        return 1
    max_num = 0
    pattern = re.compile(rf"^(\d{{3}})_{re.escape(tag)}\.json$")
    for path in archive_dir.glob("*.json"):
        m = pattern.match(path.name)
        if m:
            num = int(m.group(1))
            if num > max_num:
                max_num = num
    return max_num + 1


def cmd_run(args) -> int:
    """Run the benchmark."""
    try:
        symbols = [args.symbol] if args.symbol is not None else list(DEFAULT_SYMBOLS)
        for symbol in symbols:
            validate_symbol(symbol)
        url = stock_prices_url(args.revision)
        if args.runs < 1 or not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("runs and timeout must be positive and finite")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", args.tag):
            raise ValueError("tag must be 1-64 filename-safe characters")
    except ValueError as exc:
        return parser_error(exc)

    preflight_start = time.perf_counter()
    environment, settings = preflight()
    if args.http_proxy is not None:
        settings["http_proxy"] = args.http_proxy
    preparation_seconds = time.perf_counter() - preflight_start
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run_id = f"{timestamp}_{args.tag}_{uuid.uuid4().hex[:8]}"
    output = args.output.resolve()
    path = output / "local" / f"{run_id}.json"
    report = {
        "format_version": 1, "run_id": run_id, "tag": args.tag, "status": "running",
        "revision": args.revision, "url": url,
        "sql": fixed_query(url),
        "suite_id": run_id, "suite_symbols": symbols, "schedule": "round_robin",
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
    reports = []
    for index, symbol in enumerate(symbols, 1):
        symbol_report = {
            **report, "run_id": f"{run_id}_{index}", "symbol": symbol,
            "parameters": [symbol], "samples": [],
        }
        reports.append(symbol_report)
    write_record(path, reports)
    for trial in range(1, args.runs + 1):
        for index, report in enumerate(reports, 1):
            symbol = report["symbol"]
            print(f"[{trial}/{args.runs}] {symbol}: starting isolated cold worker", flush=True)
            with tempfile.TemporaryDirectory(prefix="stock-price-cold-") as directory:
                cache = Path(directory) / "http-cache"
                cache.mkdir()
                sample = run_worker({
                    "url": url, "symbol": symbol, "cache_directory": str(cache), "settings": settings,
                }, args.timeout)
                sample["trial"] = trial
                sample["suite_sequence"] = (trial - 1) * len(symbols) + index
                report["samples"].append(sample)
            check_consistency(report["samples"])
            write_record(path, reports)
            print(f"[{trial}/{args.runs}] {symbol} {sample['status']}: "
                  f"{sample.get('e2e_seconds', 'unavailable')} s", flush=True)
    for report in reports:
        report["status"] = "complete" if all(s["status"] == "ok" for s in report["samples"]) else "invalid"
        report["statistics"] = summarize(report["samples"]) if report["status"] == "complete" else None

        if report["statistics"]:
            print(f"{report['symbol']} median: {report['statistics']['median_seconds']:.6f} s")
    write_record(path, reports)
    print(f"Report: {path}")
    prune_local(output)
    return 0 if all(report["status"] == "complete" for report in reports) else 1


def cmd_archive(args) -> int:
    """Archive the latest local run for a tag and generate a Markdown report."""
    output = args.output.resolve()
    local_path = _latest_local_run(output, args.tag)
    if local_path is None:
        print(f"No local run found for tag '{args.tag}' in {output / 'local'}", file=sys.stderr)
        return 1

    # Determine archive name
    if args.name:
        archive_name = args.name
    else:
        seq = _next_archive_number(output, args.tag)
        archive_name = f"{seq:03d}_{args.tag}"

    print(f"Archiving {local_path.name} -> {archive_name}")
    archive_path = archive_record(local_path, output, archive_name)

    # Generate Markdown report
    md_path = archive_path.with_suffix(".md")
    render_markdown(archive_path, md_path)
    print(f"Archive: {archive_path}")
    return 0


def parser_error(msg):
    """Print error and return error code."""
    print(f"Error: {msg}", file=sys.stderr)
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run subcommand
    run_parser = subparsers.add_parser("run", help="Run benchmark trials")
    run_parser.add_argument("--symbol", help="Run only this symbol; default: AAPL, KDP, ZTS in round-robin order")
    run_parser.add_argument("--runs", type=int, default=DEFAULT_RUNS, help="Trials per symbol")
    run_parser.add_argument("--tag", default="baseline")
    run_parser.add_argument("--revision", default=DEFAULT_REVISION)
    run_parser.add_argument(
        "--http-proxy",
        help="Override the environment HTTP proxy; pass an empty string to disable it",
    )
    run_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Per-worker wall timeout in seconds")
    run_parser.add_argument("--output", type=Path, default=ROOT / "results")

    # archive subcommand
    archive_parser = subparsers.add_parser("archive", help="Archive latest local run and generate report")
    archive_parser.add_argument("--tag", default="baseline", help="Tag to find latest local run for")
    archive_parser.add_argument("--name", help="Archive name (default: auto-numbered 001_tag, 002_tag, ...)")
    archive_parser.add_argument("--output", type=Path, default=ROOT / "results")

    args = parser.parse_args()

    if args.command == "run":
        return cmd_run(args)
    elif args.command == "archive":
        return cmd_archive(args)
    else:
        parser.error(f"Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
