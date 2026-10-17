"""Measure complete public calls and distribute identical work to N workers."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import time

from benchmark.common import canonical, distribution, redact_secrets, result_fingerprint
from benchmark.e2e import plan


MAX_CACHE_PREPARATION_PASSES = 1


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
    """Use the caller for individual latency and a worker pool for batches."""
    def query(task):
        return None if stop() else call(tickers[task["symbol"]], task)

    if concurrency is None:
        rows = [query(task) for task in tasks]
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            rows = list(executor.map(query, tasks))
    return [row for row in rows if row is not None]


def prepare_cache(tasks, tickers, backend, concurrency, stop):
    """Warm the exact work once on a validated complete-file disk cache."""
    started = time.perf_counter()
    preparation = {"status": "not_ready", "concurrency": concurrency or 1,
                   "execution": "caller" if concurrency is None else "thread_pool",
                   "max_passes": MAX_CACHE_PREPARATION_PASSES, "passes": [], "errors": [],
                   "seed_sha256": backend.cache_identity()}

    def finish(status):
        preparation.update(status=status, elapsed_seconds=time.perf_counter() - started)
        return preparation

    for number in range(1, MAX_CACHE_PREPARATION_PASSES + 1):
        if stop():
            return finish("incomplete")
        pass_started = time.perf_counter()
        with backend.probe() as probe:
            rows = run_calls(tasks, tickers, concurrency, stop)
            backend.drain()
        for row in rows:
            fingerprint(row)
        errors = [row for row in rows if row["status"] == "error"]
        preparation["passes"].append({
            "number": number, "task_ids": [row["id"] for row in rows],
            "completed_tasks": len(rows), "successful_tasks": sum(row["status"] == "ok" for row in rows),
            "not_applicable_tasks": sum(row["status"] == "not_applicable" for row in rows),
            "failed_tasks": len(errors), "cache_misses": probe["misses"],
            "elapsed_seconds": time.perf_counter() - pass_started,
        })
        preparation["errors"].extend(errors)
        if errors:
            return finish("warmup_errors")
        if len(rows) != len(tasks) or stop():
            return finish("incomplete")
        backend.cache_identity()
        if probe["misses"] == 0:
            return finish("ready")
    return finish("not_ready")


def measure_latency(workload, backend, state, *, emit=None, stop=lambda: False):
    plan.validate_plan(workload)
    if state not in ("cold", "cached"):
        raise ValueError("Unknown cache state")
    seed = backend.prepare_seed() if state == "cached" else None
    rows, misses, preparation_failed = [], 0, False
    started = time.perf_counter()
    for task in plan.tasks(workload):
        if stop():
            break
        if "not_applicable" in task:
            row = call(None, task)
        else:
            backend.reset(cached=state == "cached")
            initialized = time.perf_counter()
            try:
                ticker = backend.ticker(task["symbol"])
            except Exception as exc:
                row = {key: task[key] for key in ("id", "symbol", "method", "kwargs")}
                row.update(status="error", seconds=None, stage="initialization",
                           error_type=type(exc).__name__, error=redact_secrets(str(exc)))
            else:
                initialization = time.perf_counter() - initialized
                preparation = None
                if state == "cached":
                    preparation = prepare_cache([task], {task["symbol"]: ticker}, backend, None, stop)
                    if preparation["status"] == "incomplete":
                        break
                if preparation is not None and preparation["status"] != "ready":
                    row = {key: task[key] for key in ("id", "symbol", "method", "kwargs")}
                    if preparation["errors"]:
                        error = preparation["errors"][0]
                        row.update(error_type=error["error_type"], error=error["error"])
                    else:
                        preparation_failed = True
                        row.update(error_type="CacheNotReady",
                                   error="Cache preparation did not reach a zero-request pass")
                    row.update(status="error", seconds=None, stage="cache_preparation",
                               initialization_seconds=initialization)
                elif stop():
                    break
                else:
                    with backend.probe() as probe:
                        row = call(ticker, task)
                        backend.drain()
                    if state == "cached":
                        backend.cache_identity()
                    row["initialization_seconds"] = initialization
                    row["cache_misses"] = probe["misses"]
                    if state == "cached":
                        misses += probe["misses"]
                if preparation is not None:
                    row["cache_preparation"] = preparation
            fingerprint(row)
        rows.append(row)
        if emit is not None:
            emit(row)
    result = summarize(workload, rows, time.perf_counter() - started, misses,
                       complete=len(rows) == workload["task_count"])
    if seed is not None:
        result["cache_seed"] = seed
    if state == "cached" and (misses or preparation_failed):
        result["status"] = "invalid_cache"
    return result


def measure_throughput(workload, backend, state, concurrency, *, stop=lambda: False):
    plan.validate_plan(workload)
    if state not in ("cold", "cached") or concurrency not in plan.CONCURRENCIES:
        raise ValueError("Invalid throughput scenario")
    seed = backend.prepare_seed() if state == "cached" else None
    backend.reset(cached=state == "cached")
    initialization = time.perf_counter()
    tickers = {symbol: backend.ticker(symbol) for symbol in workload["symbols"]}
    initialization = time.perf_counter() - initialization
    tasks = list(plan.tasks(workload))
    preparation = None
    if state == "cached":
        preparation = prepare_cache(tasks, tickers, backend, concurrency, stop)
        if preparation["status"] != "ready":
            status = {"not_ready": "invalid_cache", "warmup_errors": "warmup_errors",
                      "incomplete": "incomplete"}[preparation["status"]]
            return {**summarize(workload, [], 0, 0, complete=False), "status": status,
                    "stage": "cache_preparation", "warmup_errors": preparation["errors"],
                    "cache_preparation": preparation, "initialization_seconds": initialization,
                    "preparation_seconds": preparation["elapsed_seconds"], "cache_seed": seed}

    with backend.probe() as probe:
        started = time.perf_counter()
        rows = run_calls(tasks, tickers, concurrency, stop)
        elapsed = time.perf_counter() - started
        backend.drain()
    for row in rows:
        fingerprint(row)
    result = summarize(workload, rows, elapsed, probe["misses"],
                       complete=len(rows) == workload["task_count"])
    result.update(initialization_seconds=initialization,
                  preparation_seconds=preparation["elapsed_seconds"] if preparation else 0)
    if preparation is not None:
        result["cache_preparation"] = preparation
        result["cache_seed"] = seed
        backend.cache_identity()
    if state == "cached" and probe["misses"]:
        result["status"] = "invalid_cache"
    return result
