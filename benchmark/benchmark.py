"""End-to-end DefeatBeta API benchmark and immutable result archive CLI."""

import argparse
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import platform
import re
import resource
import statistics
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
import uuid


WORKER_ENTRY_NS = time.perf_counter_ns()
ROOT = Path(__file__).resolve().parent
DEFAULT_SYMBOLS = ("AAPL", "KDP", "ZTS")
DEFAULT_RUNS = 3
DEFAULT_TIMEOUT = 600.0
RESULT_MARKER = "BENCH_RESULT="
PRIMARY_METRIC = "execute_query_seconds"

SHARED_FIELDS = {
    "environment",
    "configured_settings",
    "implementation",
    "methodology",
    "result",
    "effective_settings",
    "loaded_extensions",
}
CONSISTENT_ARCHIVE_FIELDS = {
    "environment",
    "configured_settings",
    "implementation",
    "methodology",
    "revision",
    "tag",
    "requested_runs",
    "timeout_seconds",
    "resolve_direct",
    "suite_id",
    "primary_metric",
}
COMPARABLE_FIELDS = {
    "environment",
    "methodology",
    "revision",
    "requested_runs",
    "timeout_seconds",
    "suite_symbols",
    "schedule",
    "url",
    "api_call",
    "primary_metric",
}


class ApiBindings(NamedTuple):
    Configuration: type
    Ticker: type
    capture_performance: object


def validate_symbol(symbol):
    if not symbol or not symbol.strip() or any(ord(character) < 32 for character in symbol):
        raise ValueError("symbol must be nonempty and contain no control characters")
    return symbol.upper()


def redact_secrets(value):
    """Remove URL query strings and proxy credentials from persisted diagnostics."""
    if isinstance(value, dict):
        return {str(key): redact_secrets(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_secrets(item) for item in value]
    if not isinstance(value, str):
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return str(value)
    value = re.sub(r"(https?://[^\s?'\"]+)\?[^\s'\"]+", r"\1?<redacted>", value)
    return re.sub(r"(https?://)[^/@\s]+@", r"\1<redacted>@", value)


def redact_proxy(proxy):
    if not proxy:
        return proxy
    from urllib.parse import urlsplit

    parts = urlsplit(proxy)
    if not parts.scheme or not parts.hostname:
        return "<invalid>"
    port = f":{parts.port}" if parts.port is not None else ""
    return f"{parts.scheme}://{parts.hostname}{port}"


def cache_snapshot(directory):
    root = Path(directory)
    files = [path for path in root.rglob("*") if path.is_file()]
    return {
        "files": len(files),
        "bytes": sum(path.stat().st_size for path in files),
    }


def result_fingerprint(frame):
    """Hash a row multiset, including duplicates, independently of scan order."""
    schema = [(str(name), str(dtype)) for name, dtype in frame.dtypes.items()]
    rows = sorted(
        json.dumps(row, default=str, ensure_ascii=True, separators=(",", ":"))
        for row in frame.itertuples(index=False, name=None)
    )
    digest = hashlib.sha256(json.dumps(schema).encode())
    for row in rows:
        digest.update(b"\n")
        digest.update(row.encode())
    return {"rows": len(frame), "schema": schema, "sha256": digest.hexdigest()}


def load_api_bindings():
    from defeatbeta_api.client.duckdb_client import capture_performance
    from defeatbeta_api.client.duckdb_conf import Configuration
    from defeatbeta_api.data.ticker import Ticker

    return ApiBindings(
        Configuration=Configuration,
        Ticker=Ticker,
        capture_performance=capture_performance,
    )


def _event_totals(events):
    totals = {}
    counts = {}
    for event in events:
        name = event.get("name", "unknown")
        totals[name] = totals.get(name, 0) + int(event.get("duration_ns", 0))
        counts[name] = counts.get(name, 0) + 1
    return {
        name: {"seconds": duration / 1e9, "calls": counts[name]}
        for name, duration in totals.items()
    }


def _frame_records(connection, sql):
    try:
        frame = connection.execute(sql).df()
        return redact_secrets(frame.to_dict(orient="records"))
    except Exception as exc:
        return {"error": redact_secrets(str(exc))}


def validate_cold_cache_status(records):
    if not isinstance(records, list):
        raise ValueError("could not verify cache status before the measured API call")
    unexpected = []
    for record in records:
        remote_path = str(record.get("original_remote_path", ""))
        path_without_query = remote_path.split("?", 1)[0]
        if not path_without_query.endswith("/spec.json"):
            unexpected.append(remote_path or "<missing remote path>")
    if unexpected:
        raise ValueError("remote data block was cached before the measured API call")


def collect_diagnostics(ticker):
    connection = ticker.duckdb_client.connection
    settings = _frame_records(
        connection,
        "SELECT name, value FROM duckdb_settings() "
        "WHERE name LIKE 'cache_httpfs%' OR name LIKE 'http_%' "
        "OR name IN ('threads', 'memory_limit', 'parquet_metadata_cache') ORDER BY name",
    )
    if isinstance(settings, list):
        settings = {
            row.get("name"): (
                redact_proxy(row.get("value"))
                if row.get("name") == "http_proxy" else row.get("value")
            )
            for row in settings
        }
    return {
        "effective_settings": settings,
        "cache_status": _frame_records(
            connection, "SELECT * FROM cache_httpfs_cache_status_query()"
        ),
        "cache_access": _frame_records(
            connection, "SELECT * FROM cache_httpfs_cache_access_info_query()"
        ),
        "cache_profile": _frame_records(
            connection, "SELECT cache_httpfs_get_profile() AS profile"
        ),
        "loaded_extensions": _frame_records(
            connection,
            "SELECT extension_name, extension_version FROM duckdb_extensions() "
            "WHERE loaded ORDER BY extension_name",
        ),
    }


def run_api_workload(payload, api=None, diagnostics=True):
    """Run one real ``Ticker.price`` call against an isolated local cache."""
    symbol = validate_symbol(payload["symbol"])
    cache_directory = Path(payload["cache_directory"])
    if not cache_directory.is_dir() or any(cache_directory.iterdir()):
        raise ValueError("worker requires an existing, empty, isolated cache directory")

    import_started_ns = time.perf_counter_ns()
    api = api or load_api_bindings()
    imported_ns = time.perf_counter_ns()
    events = []
    configuration_values = dict(payload.get("configuration", {}))
    configuration_values["cache_httpfs_cache_directory"] = str(cache_directory)
    config = api.Configuration(**configuration_values)
    ticker = None

    with api.capture_performance(events.append):
        ticker_started_ns = time.perf_counter_ns()
        ticker = api.Ticker(
            symbol,
            http_proxy=payload.get("http_proxy"),
            log_level=logging.WARNING,
            config=config,
        )
        ticker_initialized_ns = time.perf_counter_ns()
        cache_before = cache_snapshot(cache_directory)
        if diagnostics:
            cache_status_before = _frame_records(
                ticker.duckdb_client.connection,
                "SELECT * FROM cache_httpfs_cache_status_query()",
            )
            validate_cold_cache_status(cache_status_before)
        else:
            cache_status_before = []

        query_event_offset = len(events)
        api_started_ns = time.perf_counter_ns()
        frame = ticker.price()
        api_ended_ns = time.perf_counter_ns()
        query_events = events[query_event_offset:]

    cache_after = cache_snapshot(cache_directory)
    if diagnostics:
        fingerprint = result_fingerprint(frame)
        if "symbol" not in frame or not frame["symbol"].eq(symbol).all():
            raise ValueError("Ticker.price returned data for an unexpected symbol")
        diagnostic_data = collect_diagnostics(ticker)
    else:
        fingerprint = {"rows": len(frame)}
        diagnostic_data = {}

    phase_totals = _event_totals(query_events)
    execute_query_seconds = phase_totals.get(
        "duckdb.execute_query", {"seconds": 0.0}
    )["seconds"]
    execute_attempts = phase_totals.get(
        "duckdb.execute_query", {"calls": 0}
    )["calls"]
    if diagnostics and execute_attempts < 1:
        raise ValueError("Ticker.price did not emit a DuckDBClient._execute_query event")

    usage = resource.getrusage(resource.RUSAGE_SELF)
    outcome = {
        "status": "ok" if len(frame) else "empty_result",
        "pid": os.getpid(),
        "symbol": symbol,
        "cache_directory": str(cache_directory),
        "cache_empty_at_worker_start": True,
        "cache_before_query": cache_before,
        "cache_status_before_query": cache_status_before,
        "cache_after_query": cache_after,
        "import_seconds": (imported_ns - import_started_ns) / 1e9,
        "ticker_initialization_seconds": (
            ticker_initialized_ns - ticker_started_ns
        ) / 1e9,
        "api_call_seconds": (api_ended_ns - api_started_ns) / 1e9,
        "execute_query_seconds": execute_query_seconds,
        "execute_query_attempts": execute_attempts,
        "performance": phase_totals,
        "performance_events": redact_secrets(query_events),
        "initialization_performance": redact_secrets(events[:query_event_offset]),
        "cpu_user_seconds": usage.ru_utime,
        "cpu_system_seconds": usage.ru_stime,
        "peak_rss_bytes": usage.ru_maxrss * (1 if sys.platform == "darwin" else 1024),
        "minor_faults": usage.ru_minflt,
        "major_faults": usage.ru_majflt,
        "result": fingerprint,
        **diagnostic_data,
    }
    if ticker is not None and diagnostics:
        ticker.duckdb_client.close()
    return redact_secrets(outcome)


def worker_environment(payload, base_environment=None):
    environment = dict(os.environ if base_environment is None else base_environment)
    existing_pythonpath = environment.get("PYTHONPATH")
    python_paths = [str(ROOT.parent)]
    if existing_pythonpath:
        python_paths.append(existing_pythonpath)
    environment["PYTHONPATH"] = os.pathsep.join(python_paths)
    proxy = payload.get("http_proxy")
    if proxy:
        environment.update({
            "http_proxy": proxy,
            "https_proxy": proxy,
            "HTTP_PROXY": proxy,
            "HTTPS_PROXY": proxy,
        })
    return environment


def run_worker(payload, timeout):
    request = dict(payload)
    request["parent_launch_ns"] = time.perf_counter_ns()
    try:
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "_worker"],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            timeout=timeout,
            env=worker_environment(request),
        )
    except subprocess.TimeoutExpired as exc:
        def decode(value):
            return value.decode(errors="replace") if isinstance(value, bytes) else value

        return {
            "status": "timeout",
            "timeout_seconds": timeout,
            "stdout": decode(exc.stdout),
            "stderr": decode(exc.stderr),
        }

    lines = completed.stdout.splitlines()
    messages = [line[len(RESULT_MARKER):] for line in lines if line.startswith(RESULT_MARKER)]
    try:
        if len(messages) != 1:
            raise ValueError("worker did not return exactly one result")
        sample = json.loads(messages[0])
        if completed.returncode and sample.get("status") != "error":
            raise ValueError("worker exited unsuccessfully")
        if sample.get("status") not in ("ok", "empty_result", "error"):
            raise ValueError("worker returned an unknown status")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        sample = {"status": "error", "error": str(exc)}
    sample.update({
        "returncode": completed.returncode,
        "stdout": "\n".join(line for line in lines if not line.startswith(RESULT_MARKER)),
        "stderr": completed.stderr,
        "worker_wall_seconds": (
            time.perf_counter_ns() - request["parent_launch_ns"]
        ) / 1e9,
    })
    return redact_secrets(sample)


def summarize(samples, metric=PRIMARY_METRIC):
    values = [
        float(sample[metric])
        for sample in samples
        if sample.get("status") == "ok" and metric in sample
    ]
    if not values:
        return None
    return {
        "metric": metric,
        "count": len(values),
        "median_seconds": statistics.median(values),
        "min_seconds": min(values),
        "max_seconds": max(values),
        "p95_seconds": (
            statistics.quantiles(values, n=100, method="inclusive")[94]
            if len(values) >= 20 else None
        ),
        "std_seconds": statistics.stdev(values) if len(values) > 1 else None,
    }


def pack_reports(reports):
    shared = {}
    identifiers = {}

    def encode(value):
        if isinstance(value, list):
            return [encode(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, item in value.items():
            if key in SHARED_FIELDS:
                signature = json.dumps(item, sort_keys=True)
                if signature not in identifiers:
                    identifier = f"{key}_{len(shared) + 1}"
                    identifiers[signature] = identifier
                    shared[identifier] = item
                result[key] = {"$ref": identifiers[signature]}
            else:
                result[key] = encode(item)
        return result

    return {"format_version": 2, "shared": shared, "runs": encode(reports)}


def unpack_reports(record):
    if record.get("format_version") != 2:
        raise ValueError("Unsupported record format")

    def decode(value):
        if isinstance(value, list):
            return [decode(item) for item in value]
        if isinstance(value, dict):
            if set(value) == {"$ref"}:
                return record["shared"][value["$ref"]]
            return {key: decode(item) for key, item in value.items()}
        return value

    return decode(record["runs"])


def write_record(path, reports):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
    ) as handle:
        temporary = Path(handle.name)
        json.dump(pack_reports(reports), handle, indent=2)
        handle.write("\n")
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_archive_reports(reports):
    if not reports or any(report.get("status") != "complete" for report in reports):
        raise ValueError("Only complete benchmark runs can be archived")
    for field in CONSISTENT_ARCHIVE_FIELDS:
        signatures = {json.dumps(report.get(field), sort_keys=True) for report in reports}
        if len(signatures) > 1:
            raise ValueError(f"Archive mixes different {field} values")


def _results_by_symbol(reports):
    results = {}
    for report in reports:
        symbol = report.get("symbol")
        if not symbol or symbol in results:
            raise ValueError("Each archived run must contain unique symbols")
        signatures = {
            json.dumps(sample.get("result"), sort_keys=True)
            for sample in report.get("samples", [])
            if sample.get("status") == "ok"
        }
        if len(signatures) != 1:
            raise ValueError(f"Run has inconsistent results for {symbol}")
        results[symbol] = signatures.pop()
    return results


def validate_comparison(baseline_reports, candidate_reports, allowed_differences=()):
    validate_archive_reports(baseline_reports)
    validate_archive_reports(candidate_reports)
    baseline = baseline_reports[0]
    candidate = candidate_reports[0]
    for field in COMPARABLE_FIELDS:
        if baseline.get(field) != candidate.get(field):
            raise ValueError(f"Comparison has different {field} values")

    allowed = set(allowed_differences)
    baseline_settings = baseline.get("configured_settings", {})
    candidate_settings = candidate.get("configured_settings", {})
    names = set(baseline_settings) | set(candidate_settings)
    changed = {
        name for name in names
        if baseline_settings.get(name) != candidate_settings.get(name)
    }
    unexpected = changed - allowed
    if unexpected:
        raise ValueError(
            "Comparison has undeclared setting differences: "
            + ", ".join(sorted(unexpected))
        )
    unused = allowed - changed
    if unused:
        raise ValueError(
            "Declared setting differences did not change: " + ", ".join(sorted(unused))
        )
    if _results_by_symbol(baseline_reports) != _results_by_symbol(candidate_reports):
        raise ValueError("Comparison result hashes or symbols do not match")


def _archive_name(name):
    if not re.fullmatch(r"[0-9]{3}_[A-Za-z0-9][A-Za-z0-9_-]*", name):
        raise ValueError("Archive name must look like 001_connection_reuse")
    return name


def archive_comparison(baseline_source, candidate_source, output, name,
                       allowed_differences=()):
    _archive_name(name)
    baseline = unpack_reports(json.loads(Path(baseline_source).read_text(encoding="utf-8")))
    candidate = unpack_reports(json.loads(Path(candidate_source).read_text(encoding="utf-8")))
    validate_comparison(baseline, candidate, allowed_differences)
    record = {
        "format_version": 3,
        "allowed_setting_differences": sorted(allowed_differences),
        "baseline": pack_reports(baseline),
        "candidate": pack_reports(candidate),
    }
    destination = Path(output) / "archive" / f"{name}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2)
        handle.write("\n")
    return destination


def prune_local(output, days=30, count=100, now=None):
    now = now or datetime.now(timezone.utc)
    candidates = []
    for path in (Path(output) / "local").glob("*.json"):
        if path.is_symlink():
            continue
        try:
            created = datetime.strptime(
                path.name.split("_", 1)[0], "%Y%m%dT%H%M%S.%fZ"
            ).replace(tzinfo=timezone.utc)
            reports = unpack_reports(json.loads(path.read_text(encoding="utf-8")))
            if any(report.get("status") == "running" for report in reports):
                if created >= now - timedelta(days=days):
                    continue
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
        candidates.append((created, path))
    removed = []
    for index, (created, path) in enumerate(sorted(candidates, reverse=True)):
        if index >= count or created < now - timedelta(days=days):
            path.unlink()
            removed.append(path)
    return removed


def source_hashes():
    paths = (
        ROOT / "benchmark.py",
        ROOT / "report.py",
        ROOT.parent / "defeatbeta_api" / "client" / "duckdb_client.py",
        ROOT.parent / "defeatbeta_api" / "client" / "duckdb_conf.py",
        ROOT.parent / "defeatbeta_api" / "data" / "ticker.py",
    )
    return {
        str(path.relative_to(ROOT.parent)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths if path.is_file()
    }


def environment_info():
    import duckdb
    import pandas
    import psutil

    connection = duckdb.connect(":memory:")
    extensions = connection.execute(
        "SELECT extension_name, installed, extension_version, install_path "
        "FROM duckdb_extensions() WHERE extension_name IN ('httpfs', 'cache_httpfs') "
        "ORDER BY extension_name"
    ).fetchall()
    connection.close()
    if len(extensions) != 2 or not all(row[1] for row in extensions):
        raise RuntimeError("Install httpfs and cache_httpfs before benchmarking")
    return {
        "python": sys.version,
        "executable": sys.executable,
        "duckdb": duckdb.__version__,
        "pandas": pandas.__version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "logical_cpus": os.cpu_count(),
        "physical_cpus": psutil.cpu_count(logical=False),
        "memory_bytes": psutil.virtual_memory().total,
        "extensions": [
            {
                "name": name,
                "version": version,
                "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            }
            for name, installed, version, path in extensions
        ],
    }


def cmd_run(args):
    try:
        symbols = [validate_symbol(args.symbol)] if args.symbol else list(DEFAULT_SYMBOLS)
        if args.runs < 1 or not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("runs and timeout must be positive and finite")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", args.tag):
            raise ValueError("tag must be 1-64 filename-safe characters")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    environment = environment_info()
    implementation = source_hashes()
    configuration = {
        "http_keep_alive": args.keep_alive,
        "resolve_direct": args.resolve_direct,
        "threads": args.threads,
    }
    configured_settings = {
        **configuration,
        "http_proxy": redact_proxy(args.http_proxy),
    }
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run_id = f"{timestamp}_{args.tag}_{uuid.uuid4().hex[:8]}"
    path = args.output.resolve() / "local" / f"{run_id}.json"
    common = {
        "format_version": 2,
        "suite_id": run_id,
        "suite_symbols": symbols,
        "schedule": "round_robin",
        "tag": args.tag,
        "status": "running",
        "revision": "main",
        "url": (
            "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/"
            "resolve/main/data/US/stock_prices.parquet"
        ),
        "api_call": "defeatbeta_api.data.ticker.Ticker.price",
        "resolve_direct": args.resolve_direct,
        "primary_metric": PRIMARY_METRIC,
        "requested_runs": args.runs,
        "timeout_seconds": args.timeout,
        "environment": environment,
        "implementation": implementation,
        "configured_settings": configured_settings,
        "methodology": {
            "workload": "Ticker(symbol).price() through the installed defeatbeta_api package",
            "cold": (
                "Fresh worker and isolated cache directory per sample; stock_prices cache "
                "verified absent immediately before the measured API call"
            ),
            "main_metric": (
                "Sum of DuckDBClient._execute_query timing events emitted during Ticker.price()"
            ),
            "secondary_metrics": (
                "Package import, Ticker initialization, API call, cache state, and cache_httpfs profile"
            ),
            "excluded": "Result hashing, diagnostics, report writing, and teardown",
            "uncontrolled": "DNS, proxy state, operating-system caches, and remote CDN caches",
        },
    }
    reports = [
        {
            **common,
            "run_id": f"{run_id}_{index}",
            "symbol": symbol,
            "samples": [],
            "statistics": None,
        }
        for index, symbol in enumerate(symbols, 1)
    ]
    write_record(path, reports)

    for trial in range(1, args.runs + 1):
        for index, report in enumerate(reports, 1):
            symbol = report["symbol"]
            print(f"[{trial}/{args.runs}] {symbol}: starting API benchmark", flush=True)
            with tempfile.TemporaryDirectory(prefix="defeatbeta-api-benchmark-") as directory:
                cache = Path(directory) / "http-cache"
                cache.mkdir()
                sample = run_worker(
                    {
                        "symbol": symbol,
                        "cache_directory": str(cache),
                        "http_proxy": args.http_proxy,
                        "configuration": configuration,
                    },
                    args.timeout,
                )
            sample["trial"] = trial
            sample["suite_sequence"] = (trial - 1) * len(symbols) + index
            report["samples"].append(sample)
            write_record(path, reports)
            value = sample.get(PRIMARY_METRIC, "unavailable")
            print(f"[{trial}/{args.runs}] {symbol} {sample['status']}: {value} s", flush=True)

    for report in reports:
        good = [sample for sample in report["samples"] if sample.get("status") == "ok"]
        consistent = {
            json.dumps(sample.get("result"), sort_keys=True) for sample in good
        }
        valid = len(good) == args.runs and len(consistent) == 1
        report["status"] = "complete" if valid else "invalid"
        report["statistics"] = summarize(report["samples"]) if valid else None
        if report["statistics"]:
            print(
                f"{report['symbol']} median {PRIMARY_METRIC}: "
                f"{report['statistics']['median_seconds']:.6f} s"
            )
    write_record(path, reports)
    print(f"Record: {path}")
    prune_local(args.output)
    return 0 if all(report["status"] == "complete" for report in reports) else 1


def cmd_archive(args):
    try:
        destination = archive_comparison(
            args.baseline_source,
            args.candidate_source,
            args.output.resolve(),
            args.name,
            args.allow_setting_difference,
        )
        from report import render_markdown

        render_markdown(destination, destination.with_suffix(".md"))
    except (ValueError, FileExistsError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Archive: {destination}")
    return 0


def worker_main():
    try:
        request = json.loads(sys.stdin.read())
        outcome = run_api_workload(request)
        outcome["process_start_seconds"] = (
            WORKER_ENTRY_NS - request.get("parent_launch_ns", WORKER_ENTRY_NS)
        ) / 1e9
    except Exception as exc:
        outcome = {
            "status": "error",
            "error": redact_secrets(str(exc)),
            "traceback": redact_secrets(traceback.format_exc()),
        }
    print(RESULT_MARKER + json.dumps(outcome, ensure_ascii=True), flush=True)
    return 0 if outcome["status"] in ("ok", "empty_result") else 1


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Run real Ticker.price benchmark samples")
    run_parser.add_argument("--symbol")
    run_parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    run_parser.add_argument("--tag", default="baseline")
    run_parser.add_argument("--http-proxy")
    run_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    run_parser.add_argument("--threads", type=int, default=4)
    run_parser.add_argument(
        "--keep-alive", action=argparse.BooleanOptionalAction, default=True
    )
    run_parser.add_argument(
        "--resolve-direct", action=argparse.BooleanOptionalAction, default=True
    )
    run_parser.add_argument("--output", type=Path, default=ROOT / "results")

    archive_parser = subparsers.add_parser(
        "archive", help="Publish one selected baseline-versus-candidate comparison"
    )
    archive_parser.add_argument("--baseline-source", type=Path, required=True)
    archive_parser.add_argument("--candidate-source", type=Path, required=True)
    archive_parser.add_argument("--name", required=True)
    archive_parser.add_argument(
        "--allow-setting-difference", action="append", default=[]
    )
    archive_parser.add_argument("--output", type=Path, default=ROOT / "results")
    return parser


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "_worker":
        return worker_main()
    args = build_parser().parse_args()
    if args.command == "run":
        return cmd_run(args)
    if args.command == "archive":
        return cmd_archive(args)
    raise AssertionError(f"unknown command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
