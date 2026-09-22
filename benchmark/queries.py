"""One process, one empty data cache, one fully materialized query."""

import time

WORKER_ENTRY_NS = time.perf_counter_ns()

import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import traceback

from config import validate_symbol


def fixed_query(url):
    return "SELECT * FROM '" + url.replace("'", "''") + "' WHERE symbol = ?"


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


def execute_once(payload):
    import duckdb
    import pandas  # Include result-conversion imports in initialization timing.

    validate_symbol(payload["symbol"])
    cache = Path(payload["cache_directory"])
    if not cache.is_dir() or any(cache.iterdir()):
        raise ValueError("worker requires an existing, empty, isolated cache directory")
    connection = duckdb.connect(":memory:", config={"autoinstall_known_extensions": False})
    connection.execute("LOAD cache_httpfs")
    settings = dict(payload["settings"])
    settings["cache_httpfs_cache_directory"] = str(cache)
    settings["temp_directory"] = str(cache.parent / "spill")
    for name, value in settings.items():
        connection.execute(f"SET GLOBAL {name} = ?", [value])
    initialized_ns = time.perf_counter_ns()
    frame = connection.execute(fixed_query(payload["url"]), [payload["symbol"]]).df()
    materialized_ns = time.perf_counter_ns()
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # Validation, hashing, metadata collection, and teardown are outside timing.
    fingerprint = result_fingerprint(frame)
    if "symbol" not in frame or not frame["symbol"].eq(payload["symbol"]).all():
        raise ValueError("query returned a symbol outside the requested predicate")
    effective = dict(connection.execute("SELECT name, value FROM duckdb_settings()").fetchall())
    effective = {
        key: value for key, value in effective.items()
        if key.startswith(("cache_httpfs", "http_"))
        or key in ("threads", "memory_limit", "parquet_metadata_cache", "temp_directory")
    }
    # Do not persist proxy credentials.
    if effective.get("http_proxy"):
        from urllib.parse import urlsplit
        proxy = urlsplit(effective["http_proxy"])
        effective["http_proxy"] = f"{proxy.scheme}://{proxy.hostname}:{proxy.port}"
    extensions = connection.execute(
        "SELECT extension_name, extension_version FROM duckdb_extensions() WHERE loaded ORDER BY 1"
    ).fetchall()
    cache_files = [path for path in cache.rglob("*") if path.is_file()]
    result = {
        "status": "ok" if len(frame) else "empty_result",
        "pid": os.getpid(),
        "cache_directory": str(cache),
        "cache_empty_before_query": True,
        "cache_files_after_query": len(cache_files),
        "cache_bytes_after_query": sum(path.stat().st_size for path in cache_files),
        "e2e_seconds": (materialized_ns - payload["launch_ns"]) / 1e9,
        "process_start_seconds": (WORKER_ENTRY_NS - payload["launch_ns"]) / 1e9,
        "initialization_seconds": (initialized_ns - WORKER_ENTRY_NS) / 1e9,
        "query_seconds": (materialized_ns - initialized_ns) / 1e9,
        "cpu_user_seconds": usage.ru_utime,
        "cpu_system_seconds": usage.ru_stime,
        "peak_rss_bytes": usage.ru_maxrss * (1 if sys.platform == "darwin" else 1024),
        "minor_faults": usage.ru_minflt,
        "major_faults": usage.ru_majflt,
        "result": fingerprint,
        "effective_settings": effective,
        "loaded_extensions": extensions,
        "pandas_version": pandas.__version__,
    }
    connection.close()
    return result


if __name__ == "__main__":
    try:
        request = json.loads(sys.stdin.read())
        outcome = execute_once(request)
    except Exception as exc:
        outcome = {"status": "error", "error": str(exc), "traceback": traceback.format_exc()}
    # A marker makes extension log output distinguishable from the protocol.
    print("BENCH_RESULT=" + json.dumps(outcome, ensure_ascii=True), flush=True)
    sys.exit(0 if outcome["status"] in ("ok", "empty_result") else 1)
