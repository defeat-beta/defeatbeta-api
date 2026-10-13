"""Compare process connection budgets under cached and uncached mixed queries.

Only this diagnostic changes policies, in its own process. Product defaults are
unchanged. Run candidates sequentially on one network, with reversed order in
the second round. Signed URLs, proxy credentials, and exception text are omitted.
"""

import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import logging
from pathlib import Path
import statistics
import tempfile
from threading import Lock
import time
from unittest.mock import patch

from benchmark.common import API_FILES, result_fingerprint
from benchmark.diagnostics.connection_timeline import Timeline
from benchmark.diagnostics.cache_timeline import CacheTimeline
from benchmark.diagnostics.http2_stream_timeline import StreamTimeline
from benchmark.workloads.http_pool_defaults import measure
from benchmark.common import SYMBOLS, percentile


METHODS = ("price", "info", "calendar", "dividends")
TASKS = tuple((symbol, method) for symbol in SYMBOLS for method in METHODS)


def batch_plan(concurrencies, repeats, reverse=False):
    order = list(reversed(concurrencies)) if reverse else list(concurrencies)
    return [(concurrency, repeat) for concurrency in order for repeat in range(1, repeats + 1)]


class QueueSamples:
    """Observe queue and capacity together, without inferring remote waiting."""

    def __init__(self):
        self.lock = Lock()
        self.counts = {"observations": 0, "with_pending": 0,
                       "pending_below_connection_budget": 0, "pending_while_connecting": 0,
                       "pending_at_budget_with_all_slots_reserved": 0}
        self.full_example = None

    def observe(self, state):
        connections = state["connections"]
        budget = state["configuration"]["max_connections_for_all_origins"]
        with self.lock:
            self.counts["observations"] += 1
            if state["pending_requests"]:
                self.counts["with_pending"] += 1
                self.counts["pending_below_connection_budget"] += len(connections) < budget
                self.counts["pending_while_connecting"] += any(c["state"] == "connecting" for c in connections)
                saturated = (len(connections) == budget and all(
                    c["state"] in {"ready", "busy"} and c["effective_stream_limit"] > 0
                    and c["reserved_streams"] >= c["effective_stream_limit"] for c in connections))
                if saturated:
                    self.counts["pending_at_budget_with_all_slots_reserved"] += 1
                    if self.full_example is None:
                        self.full_example = state
        return state

    def summary(self):
        return {**self.counts, "full_capacity_example": self.full_example}


def distribution(values):
    return {"samples": len(values),
            "total_seconds": sum(values),
            "p50_seconds": statistics.median(values) if values else None,
            "p95_seconds": percentile(values, 0.95) if values else None,
            "max_seconds": max(values) if values else None}


def summarize(timeline):
    """Keep distinct, potentially overlapping spans; never add them together."""
    result = {}
    for key, phase in (("worker_queue", "cache.worker_queue"),
                       ("pool_acquire", "transport.pool_wait"),
                       ("protocol_until_headers", "transport.protocol_until_headers"),
                       ("socket_read", "transport.socket_read"),
                       ("cache_publish_lock", "cache.publish_lock_wait")):
        result[key] = distribution([event["duration_ns"] / 1e9 for event in timeline.events
                                    if event["phase"] == phase])
    ranges = [request for request in timeline.requests if request.get("range")]
    for key, timestamp in (("request_until_headers", "headers_received_ns"),
                           ("request_until_first_body", "first_body_delivered_ns")):
        result[key] = distribution([(request[timestamp] - request["start_ns"]) / 1e9
                                    for request in ranges if timestamp in request])
    result["body_delivery"] = distribution([
        (request["last_body_delivered_ns"] - request["first_body_delivered_ns"]) / 1e9
        for request in ranges if "first_body_delivered_ns" in request])
    files = {}
    for request in ranges:
        file = files.setdefault(request["file"], {"requests": 0, "body_bytes": 0,
                                                   "errors": 0, "origins": set()})
        file["requests"] += 1
        file["body_bytes"] += request["body_bytes"]
        file["errors"] += "error_type" in request
        file["origins"].add(request["origin_host"])
    for file in files.values():
        file["origins"] = sorted(file["origins"])
    result.update(files=files, range_requests=len(ranges),
                  range_body_bytes=sum(request["body_bytes"] for request in ranges),
                  unattributed_range_requests=sum(request.get("query_id") is None for request in ranges),
                  recording_seconds=timeline.recording_ns / 1e9,
                  preparation_errors=sum(event.get("status") == "error"
                                         and event["phase"] in {
                                             "duckdb.prepare_parquet_metadata", "duckdb.prefetch_ranges"}
                                         for event in timeline.events))
    return result


def check_fingerprint(expected, symbol, method, fingerprint):
    key = (symbol, method)
    if key in expected and expected[key] != fingerprint:
        raise ValueError("Query result changed across paths, budgets, or rounds")
    expected[key] = fingerprint


def save(path, report):
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n")


def clear_data(client, directory):
    filesystem = client._dataset_fs
    if filesystem is None:
        return
    if filesystem.await_pending()["errors"]:
        raise RuntimeError("Pending cache downloads failed")
    with filesystem._guard:
        filesystem._memory_blocks.clear()
        filesystem._memory_access_ns.clear()
    for path in Path(directory).glob("*.block"):
        path.unlink()


def run(args):
    mode = getattr(args, "receive_mode", "coordinated")
    context = (patch("defeatbeta_api.client.http_pool.coordinate_receives", return_value=None)
               if mode == "upstream" else nullcontext())
    with context:
        return _run(args)


def _run(args):
    from defeatbeta_api.client.duckdb_conf import Configuration
    from defeatbeta_api.client.duckdb_client import capture_performance
    from defeatbeta_api.client.http_pool import configure_connection_pool, get_connection_pool_status
    from defeatbeta_api.client.shared_resources import close_network_resources
    from defeatbeta_api.data.ticker import Ticker

    if args.output.exists():
        raise FileExistsError("Benchmark output already exists")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    original = get_connection_pool_status()["configuration"]
    report = {"status": "running", "created_at": datetime.now(timezone.utc).isoformat(),
              "versions": {name: version(name) for name in ("duckdb", "httpx", "httpcore", "h2")},
              "methodology": {
                  "network": args.network_label,
                  "routing": "Existing proxy and TLS environment; unchanged",
                  "order": "Sequential candidates and batches; reverse both orders on alternate rounds",
                  "rounds": args.rounds, "concurrency": args.concurrency,
                  "batches_per_concurrency": args.batches_per_concurrency,
                  "api_files": {method: API_FILES[method] for method in METHODS},
                  "tasks": "Distinct symbol/API pairs, balanced across four files; shared default Ticker owner",
                  "fixed_policy": {"core_connections_per_origin": 4, "max_streams_per_connection": 4,
                                   "cache_fetch_workers": 16, "extra_connection_idle_timeout": 60,
                                   "max_connecting_per_origin": 4},
                  "cached": "Prepare all four footer/index objects; clear only data extents before each batch",
                  "uncached": "Use public cache_enabled=False; includes repeated footer reads and has no symbol prefetch",
                  "duckdb": "External file cache disabled; default metadata cache retained",
                  "duckdb_threads": args.duckdb_threads,
                  "connections": "Fresh pool per candidate/round; four sequential API warmups, no forced preconnections",
                  "batch_order": "First batch can expand the pool; later batches reuse earlier demand-created connections",
                  "throughput": "Application downloaded bytes, including prefetch drain; not physical link bandwidth",
                  "timing": "Spans overlap; totals are accumulated request/task time, not exclusive batch wall time",
                  "sampling": "Pool state sampled every 5 ms; transient peaks may be missed",
                  "queue_samples": "Observation counts, not time fractions; capacity and pending checked in one snapshot",
                  "instrumentation": ("Hooks disabled; per-query timers and pool sampling only"
                      if getattr(args, "no_hooks", False) else "Timeline hooks enabled; overhead not subtracted"),
                  "receive_mode": getattr(args, "receive_mode", "coordinated"),
                  "detailed_pipeline": args.detailed_pipeline,
                  "stream_events": args.stream_events,
                  "fingerprints": "Computed after timed queries; identical pairs checked across all paths and budgets",
                  "percentiles": "Empirical nearest-rank P95; observations in a batch are correlated",
              }, "sources": {}, "diagnostics": {}, "cases": []}
    for name in ("http_pool", "http_runtime", "http2_receive", "shared_resources", "dataset_cache_fs",
                 "duckdb_client", "duckdb_conf", "hugging_face_client"):
        report["sources"][name] = hashlib.sha256(Path(f"defeatbeta_api/client/{name}.py").read_bytes()).hexdigest()
    for name, path in (
        ("http_pool_mixed", "benchmark/workloads/http_pool_mixed.py"),
        ("http_pool_defaults", "benchmark/workloads/http_pool_defaults.py"),
        ("connection_timeline", "benchmark/diagnostics/connection_timeline.py"),
    ):
        report["diagnostics"][name] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if args.detailed_pipeline:
        report["diagnostics"]["cache_timeline"] = hashlib.sha256(Path("benchmark/diagnostics/cache_timeline.py").read_bytes()).hexdigest()
    if args.stream_events:
        report["diagnostics"]["http2_stream_timeline"] = hashlib.sha256(Path("benchmark/diagnostics/http2_stream_timeline.py").read_bytes()).hexdigest()
    expected = {}
    policies = [(mode, budget) for mode in args.cache_modes for budget in args.budgets]
    try:
        for round_number in range(args.rounds):
            order = policies if round_number % 2 == 0 else list(reversed(policies))
            batches = batch_plan(args.concurrency, args.batches_per_concurrency, round_number % 2 == 1)
            for mode, budget in order:
                close_network_resources()
                configure_connection_pool(core_connections_per_origin=4,
                                          max_connections_for_all_origins=budget,
                                          max_streams_per_connection=4,
                                          max_connecting_per_origin=4,
                                          extra_connection_idle_timeout=60)
                with tempfile.TemporaryDirectory() as directory:
                    client = None
                    try:
                        configuration = Configuration(cache_directory=directory, cache_enabled=mode == "cached",
                                                      duckdb_threads=args.duckdb_threads,
                                                      cache_version_check_interval_seconds=86400)
                        tickers = {symbol: Ticker(symbol, config=configuration, log_level=logging.WARNING)
                                   for symbol in SYMBOLS[:(max(args.concurrency) + 3) // 4]}
                        client = next(iter(tickers.values())).duckdb_client
                        if any(ticker.duckdb_client is not client for ticker in tickers.values()):
                            raise ValueError("Mixed queries unexpectedly use multiple filesystem owners")
                        effective_threads = client.connection.execute(
                            "SELECT current_setting('threads')").fetchone()[0]
                        if effective_threads != args.duckdb_threads:
                            raise ValueError("Requested DuckDB thread count was not applied")
                        dataset_version = client._data_update_time
                        if "dataset_version" in report and dataset_version != report["dataset_version"]:
                            raise ValueError("Dataset version changed during the benchmark")
                        report["dataset_version"] = dataset_version
                        client.connection.execute("SET enable_external_file_cache = false")
                        warmup_started = time.monotonic()
                        for method in METHODS:
                            frame = getattr(next(iter(tickers.values())), method)()
                            check_fingerprint(expected, SYMBOLS[0], method, result_fingerprint(frame))
                        warmup_seconds = time.monotonic() - warmup_started
                        for batch_number, (concurrency, repeat) in enumerate(batches, 1):
                            clear_data(client, directory)
                            filesystem = client._dataset_fs if mode == "cached" else client._uncached_fs
                            downloaded_before = filesystem.metrics()["downloaded_bytes"]
                            timeline = (StreamTimeline() if args.stream_events else
                                        CacheTimeline() if args.detailed_pipeline else Timeline())
                            timeline.label = f"round{round_number + 1}_{mode}_{budget}_{concurrency}"
                            before = get_connection_pool_status()
                            queue_samples = QueueSamples()

                            def query(index):
                                symbol, method = TASKS[index]
                                with timeline.query(symbol=symbol, api=method) as observation:
                                    with (nullcontext() if getattr(args, "no_hooks", False)
                                          else capture_performance(timeline.capture_performance)):
                                        frame = getattr(tickers[symbol], method)()
                                return {"symbol": symbol, "api": method, "query_id": observation["id"], "frame": frame}

                            hooks = (timeline.installed(filesystems=[filesystem]) if args.detailed_pipeline
                                     else timeline.installed())
                            if getattr(args, "no_hooks", False):
                                hooks = nullcontext()
                            with hooks:
                                case = measure(query, concurrency,
                                               lambda: queue_samples.observe(get_connection_pool_status()))
                                drain_started = time.monotonic()
                                drain = filesystem.await_pending()
                                drain_seconds = time.monotonic() - drain_started
                            if drain["errors"]:
                                raise RuntimeError("Measured prefetch downloads failed")
                            downloaded = filesystem.metrics()["downloaded_bytes"] - downloaded_before
                            observations = {item["id"]: item for item in timeline.queries}
                            for index, item in enumerate(case["results"]):
                                symbol, method = TASKS[index]
                                item.update(symbol=symbol, api=method)
                                if "error_type" in item:
                                    continue
                                item["fingerprint"] = result_fingerprint(item.pop("frame"))
                                check_fingerprint(expected, symbol, method, item["fingerprint"])
                                item["http_overlap"] = timeline.query_summary(observations[item["query_id"]])
                            case.update(round=round_number + 1, cache_mode=mode, max_connections=budget,
                                        duckdb_threads=args.duckdb_threads,
                                        batch_number=batch_number, warmup_seconds=warmup_seconds,
                                        repeat=repeat, queue_samples=queue_samples.summary(),
                                        initial_connections=len(before["connections"]),
                                        prefetch_drain_seconds=drain_seconds, downloaded_bytes=downloaded,
                                        bytes_per_second=downloaded / (case["wall_seconds"] + drain_seconds),
                                        timing=summarize(timeline),
                                        cached_fallback=mode == "cached" and client._uncached_fs is not None)
                            if args.detailed_pipeline:
                                case["pipeline"] = timeline.artifact()
                            case["by_api"] = {}
                            for method in METHODS:
                                selected = [item for item in case["results"] if item["api"] == method]
                                case["by_api"][method] = {**distribution([item["seconds"] for item in selected]),
                                                          "failed_queries": sum("error_type" in item for item in selected)}
                            report["cases"].append(case)
                            save(args.output, report)
                            print(f"round={round_number + 1} mode={mode} budget={budget} queries={concurrency} repeat={repeat} "
                                  f"p50={case['p50_seconds']:.3f} p95={case['p95_seconds']:.3f} "
                                  f"MBps={case['bytes_per_second'] / 1e6:.3f} connections={case['peak_connections']} "
                                  f"slots={case['peak_reserved_streams']} pending={case['peak_pending_requests']} "
                                  f"worker_wait={case['timing']['worker_queue']['total_seconds']:.3f} "
                                  f"pool_wait={case['pool_wait_seconds']:.3f} failed={case['failed_requests']}", flush=True)
                    finally:
                        if client is not None:
                            client.close()
                        close_network_resources()
        invalid = any(case["failed_requests"] or case["cached_fallback"]
                      or case["timing"]["preparation_errors"] for case in report["cases"])
        report["status"] = "complete_with_errors" if invalid else "complete"
    except BaseException as exc:
        report.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        close_network_resources()
        configure_connection_pool(**original)
        save(args.output, report)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--network-label", required=True)
    parser.add_argument("--budgets", type=int, nargs="+", default=[16, 32])
    parser.add_argument("--concurrency", type=int, nargs="+", default=[32, 64, 128])
    parser.add_argument("--cache-modes", choices=["cached", "uncached"], nargs="+", default=["cached", "uncached"])
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--batches-per-concurrency", type=int, default=1)
    parser.add_argument("--duckdb-threads", type=int, default=4,
                        help="Benchmark-only query execution control; product defaults are unchanged")
    parser.add_argument("--detailed-pipeline", action="store_true",
                        help="Retain download-task, bridge, lock, and raw event diagnostics")
    parser.add_argument("--stream-events", action="store_true",
                        help="Also trace decoded HTTP/2 event enqueue, dequeue and delivery")
    parser.add_argument("--receive-mode", choices=["coordinated", "upstream"], default="coordinated",
                        help="Benchmark-only control: bypass the receive adapter for an upstream baseline")
    parser.add_argument("--no-hooks", action="store_true",
                        help="Disable protocol/cache instrumentation; retain query timers and pool sampling")
    args = parser.parse_args()
    args.detailed_pipeline = args.detailed_pipeline or args.stream_events
    if args.no_hooks and args.detailed_pipeline:
        parser.error("Detailed diagnostics cannot be combined with --no-hooks")
    if (args.duckdb_threads < 1 or args.rounds < 1 or args.batches_per_concurrency < 1 or any(n < 4 for n in args.budgets)
            or any(n < 1 or n > len(TASKS) for n in args.concurrency)):
        parser.error("Threads and rounds must be positive, budgets at least four, and query concurrency between one and 128")
    return args


if __name__ == "__main__":
    run(parse_args())
