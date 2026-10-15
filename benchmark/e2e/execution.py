"""Measure complete public calls and distribute identical work to N workers."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import time

from benchmark.common import canonical, distribution, redact_secrets, result_fingerprint
from benchmark.e2e import plan


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


def measure_latency(workload, backend, state, *, emit=None, stop=lambda: False):
    plan.validate_plan(workload)
    if state not in ("cold", "cached"):
        raise ValueError("Unknown cache state")
    rows, misses = [], 0
    started = time.perf_counter()
    for task in plan.tasks(workload):
        if stop():
            break
        if "not_applicable" in task:
            row = call(None, task)
        else:
            backend.reset()
            initialized = time.perf_counter()
            try:
                ticker = backend.ticker(task["symbol"])
            except Exception as exc:
                row = {key: task[key] for key in ("id", "symbol", "method", "kwargs")}
                row.update(status="error", seconds=None, stage="initialization",
                           error_type=type(exc).__name__, error=redact_secrets(str(exc)))
            else:
                initialization = time.perf_counter() - initialized
                warmup = None
                if state == "cached":
                    warmup = call(ticker, task)
                    fingerprint(warmup)
                    backend.drain()
                if warmup is not None and warmup["status"] == "error":
                    row = {**warmup, "stage": "warmup", "initialization_seconds": initialization}
                elif stop():
                    break
                else:
                    with backend.probe() as probe:
                        row = call(ticker, task)
                        backend.drain()
                    row["initialization_seconds"] = initialization
                    row["cache_misses"] = probe["misses"]
                    if state == "cached":
                        misses += probe["misses"]
            fingerprint(row)
        rows.append(row)
        if emit is not None:
            emit(row)
    result = summarize(workload, rows, time.perf_counter() - started, misses,
                       complete=len(rows) == workload["task_count"])
    if state == "cached" and misses:
        result["status"] = "invalid_cache"
    return result


def measure_throughput(workload, backend, state, concurrency, *, stop=lambda: False):
    plan.validate_plan(workload)
    if state not in ("cold", "cached") or concurrency not in plan.CONCURRENCIES:
        raise ValueError("Invalid throughput scenario")
    backend.reset()
    initialization = time.perf_counter()
    tickers = {symbol: backend.ticker(symbol) for symbol in workload["symbols"]}
    initialization = time.perf_counter() - initialization
    warmup_started = time.perf_counter()
    warmup_errors = []
    if state == "cached":
        for task in plan.tasks(workload):
            if stop():
                result = summarize(workload, [], 0, 0, complete=False)
                result["stage"] = "warmup"
                return result
            row = fingerprint(call(tickers[task["symbol"]], task))
            if row["status"] == "error":
                warmup_errors.append(row)
        backend.drain()
    preparation = time.perf_counter() - warmup_started
    if warmup_errors:
        return {**summarize(workload, [], 0, 0, complete=False),
                "status": "warmup_errors", "warmup_errors": warmup_errors,
                "initialization_seconds": initialization, "preparation_seconds": preparation}

    def query(task):
        return None if stop() else call(tickers[task["symbol"]], task)

    with backend.probe() as probe:
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            rows = [row for row in executor.map(query, plan.tasks(workload)) if row is not None]
        elapsed = time.perf_counter() - started
        backend.drain()
    for row in rows:
        fingerprint(row)
    result = summarize(workload, rows, elapsed, probe["misses"],
                       complete=len(rows) == workload["task_count"])
    result.update(initialization_seconds=initialization, preparation_seconds=preparation)
    if state == "cached" and probe["misses"]:
        result["status"] = "invalid_cache"
    return result
