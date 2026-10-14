"""Disposable worker run by a product's isolated interpreter."""

from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import logging
from pathlib import Path
import sys
from threading import Barrier
import time
import traceback

from benchmark.adapter import clear_data, dataset_endpoint, snapshot
from benchmark.common import distribution, environment_info, redact_secrets, result_fingerprint, source_hashes
from benchmark.suite import coverage, invoke


MARKER = "BENCHMARK_RESULT="


def difference(after, before):
    return {key: after[key] - before[key] for key in before}


def run(payload):
    import psutil
    import defeatbeta_api
    from defeatbeta_api.client.duckdb_conf import Configuration
    from defeatbeta_api.client.duckdb_client import capture_performance
    from defeatbeta_api.data.ticker import Ticker

    source = Path(payload["source"]).resolve()
    if Path(defeatbeta_api.__file__).resolve().parent.parent != source:
        raise RuntimeError("Product import escaped the selected source snapshot")
    if source_hashes(source) != payload["source_hashes"]:
        raise RuntimeError("Product sources changed after environment preparation")
    env = environment_info()
    if env["dependencies"] != payload["dependencies"]:
        raise RuntimeError("Measured dependency versions differ from the prepared environment")
    case = payload["case"]
    cache_policy = case.get("cache_policy", "default")
    if cache_policy not in ("default", "project-only"):
        raise ValueError("Unknown cache policy")
    if case.get("state") == "metadata_ready" and cache_policy != "project-only":
        raise ValueError("Metadata-only preparation requires the project-only cache diagnostic")
    diagnostic_options = case.get("diagnostics")
    memory = []
    if diagnostic_options:
        from benchmark.diagnostics.query_observation import (
            collect_memory, memory_sample, profile_calls, validate_options,
        )
        diagnostic_options = validate_options(case)
    tasks = case["tasks"]
    directory = payload["cache_directory"]
    config = Configuration(cache_directory=directory)
    options = {"config": config, "log_level": logging.WARNING}
    pool_status = None
    if importlib.util.find_spec("defeatbeta_api.client.http_pool") is not None:
        from defeatbeta_api.client.http_pool import get_connection_pool_status
        pool_status = get_connection_pool_status
    process = psutil.Process()
    if diagnostic_options:
        memory.append(memory_sample(process, "before_constructor"))
    first = None
    with dataset_endpoint(payload.get("endpoint")):
        try:
            cpu_initial = process.cpu_times()
            init_started = time.perf_counter()
            first = Ticker(tasks[0]["symbol"], **options)
            initialization = time.perf_counter() - init_started
            cpu_initialized = process.cpu_times()
            client, fs = first.duckdb_client, first.duckdb_client._dataset_fs
            if fs is None:
                raise RuntimeError("The default product cache is unavailable")
            initial_cache = client.connection.execute(
                "SELECT current_setting('enable_external_file_cache')").fetchone()[0]
            if cache_policy == "project-only":
                client.connection.execute("SET enable_external_file_cache = false")
            engine_cache = {"policy": cache_policy, "initial_external_file_cache": initial_cache,
                            "effective_external_file_cache": client.connection.execute(
                                "SELECT current_setting('enable_external_file_cache')").fetchone()[0]}
            tickers = {tasks[0]["symbol"]: first}
            for task in tasks:
                if task["symbol"] not in tickers:
                    tickers[task["symbol"]] = Ticker(task["symbol"], **options)
            if payload.get("action") == "discover":
                resolved = []
                for task in tasks:
                    task = dict(task)
                    ticker = tickers[task["symbol"]]
                    if task["method"] == "transcript_body":
                        frame = ticker.earning_call_transcripts().get_transcripts_list()
                        if frame.empty:
                            raise ValueError("Selected symbol has no transcript body")
                        row = frame.sort_values(["fiscal_year", "fiscal_quarter"]).iloc[-1]
                        task.update(fiscal_year=int(row["fiscal_year"]), fiscal_quarter=int(row["fiscal_quarter"]))
                    elif task["method"] == "news_body":
                        frame = ticker.news().get_news_list()
                        if frame.empty:
                            raise ValueError("Selected symbol has no news body")
                        task["uuid"] = str(frame.sort_values(["report_date", "uuid"]).iloc[-1]["uuid"])
                    resolved.append(task)
                return {"status": "ok", "tasks": resolved, "engine_cache": engine_cache,
                        "dataset_version": client._data_update_time,
                        "coverage": coverage(Ticker), "environment": env}
            if case["state"] in ("memory_warm", "metadata_ready"):
                # Materialize every distinct file/API path, with duplicate paths collapsed.
                seen = set()
                for task in tasks:
                    if task["method"] not in seen:
                        invoke(tickers[task["symbol"]], task)
                        seen.add(task["method"])
                if fs.await_pending()["errors"]:
                    raise RuntimeError("Warmup prefetch failed")
                if case["state"] == "metadata_ready":
                    clear_data(fs, directory)
            state_before = snapshot(directory)
            if diagnostic_options:
                memory.append(memory_sample(process, "before_query", fs))
            if case["state"] == "first_use" and any(v["files"] for v in state_before.values()):
                raise RuntimeError("First-use data cache is not empty")
            if case["state"] == "metadata_ready" and state_before["block"]["files"]:
                raise RuntimeError("Metadata-ready query has cached data extents")
            if case["state"] == "disk_warm" and not any(v["files"] for v in state_before.values()):
                raise RuntimeError("Restarted disk-warm cache is empty")
            pool_before = pool_status() if pool_status else None
            before = fs.metrics()
            cpu_before = process.cpu_times()
            barrier = Barrier(case["concurrency"]) if case["kind"] == "burst" else None

            def query(task, submitted):
                admitted = time.perf_counter()
                if barrier is not None:
                    barrier.wait(timeout=60)
                started = time.perf_counter()
                timings = []

                def record(event):
                    if event["name"] in ("duckdb.execute_query", "duckdb.prepare_parquet_metadata"):
                        timings.append({"name": event["name"], "seconds": event["duration_ns"] / 1e9})

                try:
                    with capture_performance(record):
                        repetitions = (diagnostic_options or {}).get("profile_repeats", 0)
                        if repetitions:
                            frame, profile = profile_calls(
                                lambda: invoke(tickers[task["symbol"]], task), repetitions)
                        else:
                            frame, profile = invoke(tickers[task["symbol"]], task), None
                    outcome = {"task": task, "seconds": time.perf_counter() - started,
                               "generator_queue_seconds": admitted - submitted, "frame": frame, "timings": timings}
                    if profile is not None:
                        outcome["profile"] = profile
                    return outcome
                except Exception as exc:
                    return {"task": task, "seconds": time.perf_counter() - started,
                            "generator_queue_seconds": admitted - submitted,
                            "error_type": type(exc).__name__, "error": redact_secrets(str(exc))}

            started = time.perf_counter()
            if case["kind"] == "single":
                results = [query(tasks[0], started)]
            else:
                with ThreadPoolExecutor(max_workers=case["concurrency"]) as executor:
                    futures = [executor.submit(query, task, time.perf_counter()) for task in tasks]
                    results = [future.result() for future in futures]
            wall = time.perf_counter() - started
            cpu_after = process.cpu_times()
            rss = process.memory_info().rss
            query_delta = difference(fs.metrics(), before)
            drain_started = time.perf_counter()
            drain = fs.await_pending()
            drain_seconds = time.perf_counter() - drain_started
            pool_after = pool_status() if pool_status else None
            if diagnostic_options:
                memory.append(memory_sample(process, "after_query_and_drain", fs, client))
            for result in results:
                if "frame" in result:
                    result["result"] = result_fingerprint(result.pop("frame"))
            if diagnostic_options:
                memory.append(collect_memory(process, "after_results_released"))
            failed = sum("error_type" in result for result in results)
            result = {"status": "ok" if not failed and not drain["errors"] else "error",
                      "engine_cache": engine_cache,
                      "environment": env, "defaults": vars(config),
                      "dataset_version": client._data_update_time,
                      "file_metadata": client._footer_index,
                      "cache_before": state_before, "cache_after": snapshot(directory),
                      "initialization_seconds": initialization,
                      "first_result_seconds": initialization + wall if case["state"] in ("first_use", "disk_warm") else None,
                      "wall_seconds": wall, "latency": distribution([item["seconds"] for item in results]),
                      "completed_calls_per_second": (len(results) - failed) / wall if wall else None,
                      "failed_calls": failed, "cpu_seconds": cpu_after.user + cpu_after.system - cpu_before.user - cpu_before.system,
                      "initialization_cpu_seconds": cpu_initialized.user + cpu_initialized.system - cpu_initial.user - cpu_initial.system,
                      "preparation_cpu_seconds": cpu_before.user + cpu_before.system - cpu_initialized.user - cpu_initialized.system,
                      "rss_bytes_at_query_end": rss, "cache_query_delta": query_delta,
                      "cache_total_delta": difference(fs.metrics(), before),
                      "prefetch_drain_seconds": drain_seconds, "prefetch_errors": drain["errors"],
                      "pool_before": pool_before, "pool_after": pool_after, "results": results}
            if diagnostic_options:
                result["diagnostics"] = {"memory": memory,
                    "instrumented": bool(diagnostic_options.get("profile_repeats")),
                    "memory_scope": "RSS milestones, not peak memory or proof of a leak"}
            return result
        finally:
            if first is not None:
                first.duckdb_client.close()
                if diagnostic_options:
                    memory.append(collect_memory(process, "after_client_closed"))


if __name__ == "__main__":
    try:
        result = run(json.loads(sys.stdin.read()))
    except Exception as exc:
        result = {"status": "error", "error_type": type(exc).__name__, "traceback": redact_secrets(traceback.format_exc())}
    print(MARKER + json.dumps(redact_secrets(result), ensure_ascii=True, allow_nan=False), flush=True)
    raise SystemExit(0 if result["status"] == "ok" else 1)
