"""Measure complete public calls and distribute identical work to N workers."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import time

from benchmark.common import canonical, distribution, redact_secrets, result_fingerprint
from benchmark.e2e import plan
from benchmark.e2e.probe import CachePreparationError


def invoke(ticker, task):
    target = ticker
    parts = task["call"].split(".")
    for part in parts[:-1]:
        target = getattr(target, part)()
    value = getattr(target, parts[-1])(**task["kwargs"])
    materialize = getattr(value, "df", None)
    return materialize() if callable(materialize) else value


def call(ticker, task, *, clock=time.perf_counter):
    row = {key: task[key] for key in ("id", "symbol", "method", "kwargs")}
    if "not_applicable" in task:
        return {**row, "status": "not_applicable", "seconds": None,
                "reason": task["not_applicable"]}
    started = clock()
    try:
        value = invoke(ticker, task)
    except Exception as exc:
        elapsed = clock() - started
        return {**row, "status": "error", "seconds": elapsed,
                "error_type": type(exc).__name__, "error": redact_secrets(str(exc))}
    elapsed = clock() - started
    return {**row, "status": "ok", "seconds": elapsed, "value": value}


def fingerprint(row):
    if "value" in row:
        value = row.pop("value")
        if hasattr(value, "columns") and hasattr(value, "itertuples"):
            row["fingerprint"] = result_fingerprint(value)
        else:
            encoded = json.dumps(canonical(value), sort_keys=True, ensure_ascii=True,
                                 separators=(",", ":"), allow_nan=False).encode()
            row["fingerprint"] = {"sha256": hashlib.sha256(encoded).hexdigest(),
                                  "type": type(value).__name__}
    return row


def validate_ledger(workload, rows):
    expected = {task["id"] for task in plan.tasks(workload)}
    actual = [row["id"] for row in rows]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Incomplete or duplicate completion ledger")


def summarize(workload, rows, elapsed, misses, *, complete=True):
    if complete:
        validate_ledger(workload, rows)
    failed = sum(row["status"] == "error" for row in rows)
    successful = sum(row["status"] == "ok" for row in rows)
    return {"status": "incomplete" if not complete else "query_errors" if failed else "complete",
            "expected_tasks": workload["task_count"], "completed_tasks": len(rows),
            "successful_tasks": successful, "failed_tasks": failed,
            "not_applicable_tasks": sum(row["status"] == "not_applicable" for row in rows),
            "wall_seconds": elapsed, "successful_calls_per_second": successful / elapsed if elapsed else None,
            "latency": distribution([row["seconds"] for row in rows if row["status"] == "ok"]),
            "cache_misses": misses, "results": rows}


def run_calls(tasks, tickers, concurrency, stop):
    def query(task):
        return None if stop() else call(tickers[task["symbol"]], task)

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        rows = list(executor.map(query, tasks))
    return [row for row in rows if row is not None]


def run_pass(tasks, tickers, backend, concurrency, stop):
    """Time one whole execution, then drain and fingerprint outside timing."""
    probe, rows, elapsed = {}, [], 0.0
    try:
        with backend.probe() as probe:
            started = time.perf_counter()
            rows = run_calls(tasks, tickers, concurrency, stop)
            elapsed = time.perf_counter() - started
            backend.drain()
    except Exception as exc:
        for row in rows:
            fingerprint(row)
        failure = CachePreparationError("query_execution", exc, probe)
        failure.evidence.update(results=rows, wall_seconds=elapsed)
        raise failure from exc
    for row in rows:
        fingerprint(row)
    return rows, elapsed, probe


def measure_throughput(workload, backend, state, concurrency, *, stop=lambda: False):
    """Run one timed batch from an empty cache or from a previous batch's disk cache."""
    plan.validate_plan(workload)
    if state not in ("cold", "disk_reuse") or concurrency not in plan.CONCURRENCIES:
        raise ValueError("Invalid throughput scenario")
    if state == "disk_reuse":
        backend.reset(preserve_disk=True)
    else:
        backend.reset()
    initialization = time.perf_counter()
    tickers = {symbol: backend.ticker(symbol) for symbol in workload["symbols"]}
    initialization = time.perf_counter() - initialization
    tasks = list(plan.tasks(workload))
    rows, elapsed, probe = run_pass(tasks, tickers, backend, concurrency, stop)
    result = summarize(workload, rows, elapsed, probe["metrics"]["cache_misses"],
                       complete=len(rows) == workload["task_count"])
    result.update(initialization_seconds=initialization, requests=probe)
    return result
