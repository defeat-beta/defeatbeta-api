"""Compare query workloads with the committed baseline in isolated processes."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, nullcontext
from datetime import datetime, timezone
import hashlib
import importlib.abc
import importlib.util
import json
import logging
import math
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

import psutil

from benchmark.benchmark import result_fingerprint
from benchmark.diagnostics.connection_timeline import Timeline


def write_report(path, report):
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n")


SYMBOLS = ("PDD", "BABA", "KDP", "ZTS", "AAPL", "MSFT", "AMZN", "NVDA",
           "META", "GOOG", "TSLA", "JPM", "V", "MA", "WMT", "COST",
           "UNH", "XOM", "JNJ", "PG", "HD", "BAC", "ABBV", "KO",
           "PEP", "AVGO", "ORCL", "NFLX", "CRM", "AMD", "DIS", "INTC")


class BaselineFinder(importlib.abc.MetaPathFinder):
    def __init__(self, directory):
        self.paths = {}
        for name in ("dataset_cache_fs", "duckdb_client", "hugging_face_client"):
            relative = f"defeatbeta_api/client/{name}.py"
            source = subprocess.check_output(["git", "show", f"HEAD:{relative}"], text=True)
            if not source.isascii():
                raise ValueError("Baseline sources must contain English text only")
            path = Path(directory) / f"{name}.py"
            path.write_text(source)
            self.paths[f"defeatbeta_api.client.{name}"] = path

    def find_spec(self, fullname, path=None, target=None):
        if fullname in self.paths:
            return importlib.util.spec_from_file_location(fullname, self.paths[fullname])
        return None


def percentile(values, fraction):
    """Use the empirical nearest-rank percentile and expose sample counts."""
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def run(output, baseline=False, capacity=None, concurrencies=(1, 2, 4, 8, 16, 32),
        repeats=1, sequential_samples=0, idle_seconds=0, instrumented=True):
    if output.exists():
        raise FileExistsError("Benchmark output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        source_directory = stack.enter_context(tempfile.TemporaryDirectory())
        if baseline:
            finder = BaselineFinder(source_directory)
            sys.meta_path.insert(0, finder)
            stack.callback(sys.meta_path.remove, finder)
        from defeatbeta_api.client.duckdb_conf import Configuration
        from defeatbeta_api.client.duckdb_client import DuckDBClient, capture_performance
        from defeatbeta_api.data.ticker import Ticker

        sources = {}
        for name in ("dataset_cache_fs", "duckdb_client", "hugging_face_client"):
            path = Path(sys.modules[f"defeatbeta_api.client.{name}"].__file__)
            if baseline and path.parent != Path(source_directory):
                raise RuntimeError("Baseline source selection was not applied")
            sources[name] = hashlib.sha256(path.read_bytes()).hexdigest()

        if not baseline:
            from defeatbeta_api.client import shared_resources
            if capacity is not None:
                from defeatbeta_api.client.http_pool import configure_connection_pool
                configure_connection_pool(core_connections_per_origin=min(2, capacity),
                                          max_connections_for_all_origins=capacity)
            stack.callback(shared_resources.close_network_resources)
        cache = stack.enter_context(tempfile.TemporaryDirectory())
        configuration = Configuration(cache_directory=cache)
        timeline = Timeline()
        report = {
            "status": "running", "created_at": datetime.now(timezone.utc).isoformat(),
            "baseline": baseline, "capacity": capacity,
            "instrumented": instrumented,
            "sources": sources,
            "baseline_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "methodology": {
                "routing": "Existing environment proxy semantics, unchanged",
                "cache": "Isolated directory; footer retained; data blocks cleared between cold batches",
                "samples": f"{repeats} batches per concurrency; empirical P95, not a population estimate",
                "scope": "Current measured network route and dataset, not a universal speed claim",
                "spans": "Nested/parallel waits overlap. Time outside observed HTTP is not pure CPU",
                "ttfb": "First body delivery to the application, not packet arrival at the NIC",
            },
            "phases": [], "requests": timeline.requests, "events": timeline.events,
            "queries": timeline.queries,
        }
        clients = []
        try:
            if instrumented:
                stack.enter_context(timeline.installed())
            timeline.label = "cold_initialization"
            started = time.monotonic()
            with timeline.query(api="constructor", symbol="PDD") as constructor:
                with (capture_performance(timeline.capture_performance) if instrumented else nullcontext()):
                    first = Ticker("PDD", config=configuration, log_level=logging.WARNING)
            report["constructor_seconds"] = time.monotonic() - started
            report["constructor_query_id"] = constructor["id"]
            clients.append(first.duckdb_client)
            # Isolate the project's cache from DuckDB's additional file cache.
            first.duckdb_client.connection.execute("SET enable_external_file_cache = false")
            timeline.label = "initial_price"
            started = time.monotonic()
            with timeline.query(api="price", symbol="PDD") as initial_query:
                with (capture_performance(timeline.capture_performance) if instrumented else nullcontext()):
                    initial = first.price()
            report["initial_price_seconds"] = time.monotonic() - started
            report["initial_query_id"] = initial_query["id"]
            report["initial_result"] = result_fingerprint(initial)
            report["dataset_version"] = first.duckdb_client._data_update_time
            tickers = [first, *(Ticker(symbol, config=configuration, log_level=logging.WARNING)
                               for symbol in SYMBOLS[1:])]

            def clear_data():
                for client in clients:
                    filesystem = client._dataset_fs
                    filesystem.await_pending()
                    with filesystem._guard:
                        filesystem._memory_blocks.clear()
                        filesystem._memory_access_ns.clear()
                for path in Path(cache).glob("*.block"):
                    path.unlink()

            process = psutil.Process()

            def phase(name, selected, methods, workers):
                timeline.label = name
                event_offset = len(timeline.events)
                cpu_before = process.cpu_times()
                started = time.monotonic()
                metric_before = sum(client._dataset_fs.metrics()["downloaded_bytes"] for client in clients)

                def query(pair):
                    ticker, method = pair
                    began = time.monotonic()
                    with timeline.query(api=method, symbol=ticker.ticker) as observation:
                        with (capture_performance(timeline.capture_performance) if instrumented else nullcontext()):
                            frame = getattr(ticker, method)()
                    seconds = time.monotonic() - began
                    return {"symbol": ticker.ticker, "api": method, "seconds": seconds,
                            "query_id": observation["id"], "frame": frame}

                with ThreadPoolExecutor(max_workers=workers) as executor:
                    results = list(executor.map(query, zip(selected, methods)))
                elapsed = time.monotonic() - started
                cpu_after = process.cpu_times()
                drain_started = time.monotonic()
                for client in clients:
                    client._dataset_fs.await_pending()
                drain_seconds = time.monotonic() - drain_started
                for result in results:
                    result["result"] = result_fingerprint(result.pop("frame"))
                    observation = next(query for query in timeline.queries if query["id"] == result["query_id"])
                    result["timing"] = timeline.query_summary(observation) if instrumented else None
                events = timeline.events[event_offset:]
                requests = [request for request in timeline.requests if request["step"] == name]
                downloaded = sum(client._dataset_fs.metrics()["downloaded_bytes"] for client in clients) - metric_before
                durations = sorted(item["seconds"] for item in results)
                item = {
                    "name": name, "workers": workers, "wall_seconds": elapsed,
                    "median_seconds": statistics.median(durations),
                    "p95_seconds": percentile(durations, 0.95), "samples": len(durations),
                    "cpu_seconds": cpu_after.user + cpu_after.system - cpu_before.user - cpu_before.system,
                    "rss_bytes": process.memory_info().rss, "results": results,
                    "downloaded_bytes": downloaded,
                    "prefetch_drain_seconds": drain_seconds,
                    "application_bytes_per_second": downloaded / (elapsed + drain_seconds),
                    "tcp_connects": sum(event["phase"] == "transport.tcp_connect" for event in events) if instrumented else None,
                    "tls_handshakes": sum(event["phase"] == "transport.tls_handshake" for event in events) if instrumented else None,
                    "unattributed_requests": sum(request.get("query_id") is None for request in requests) if instrumented else None,
                    "connection_ids": sorted({request["connection_id"] for request in requests
                                               if "connection_id" in request}) if instrumented else None,
                }
                for key, event_phase in (
                    ("pool_wait_seconds", "transport.pool_wait"),
                    ("stream_wait_seconds", "transport.h2_stream_wait"),
                    ("connect_lock_wait_seconds", "transport.connect_lock_wait"),
                    ("h2_read_lock_wait_seconds", "transport.h2_read_lock_wait"),
                    ("h2_write_lock_wait_seconds", "transport.h2_write_lock_wait"),
                ):
                    item[key] = sum(event["duration_ns"] / 1e9 for event in events
                                    if event["phase"] == event_phase) if instrumented else None
                for key, timestamp in (("ttfb", "first_body_delivered_ns"),
                                       ("until_headers", "headers_received_ns")):
                    values = [(request[timestamp] - request["start_ns"]) / 1e9 for request in requests
                              if timestamp in request and request.get("range")]
                    item[key + "_samples"] = len(values)
                    item[key + "_p50_seconds"] = statistics.median(values) if values else None
                    item[key + "_p95_seconds"] = percentile(values, 0.95) if values else None
                report["phases"].append(item)
                write_report(output, report)
                print(f"phase={name} seconds={elapsed:.3f} tcp={item['tcp_connects']} "
                      f"median={item['median_seconds']:.3f}", flush=True)

            for concurrency in concurrencies:
                selected = tickers[:concurrency]
                for repeat in range(repeats):
                    suffix = f"_r{repeat + 1}" if repeats > 1 else ""
                    clear_data()
                    phase(f"price_cold_{concurrency}{suffix}", selected, ["price"] * concurrency, concurrency)
                    phase(f"price_hot_{concurrency}{suffix}", selected, ["price"] * concurrency, concurrency)
            if sequential_samples:
                clear_data()
                selected = tickers[:sequential_samples]
                phase("price_sequential", selected, ["price"] * len(selected), 1)
            clear_data()
            for repeat in range(repeats):
                suffix = f"_r{repeat + 1}" if repeats > 1 else ""
                clear_data()
                phase("mixed_files" + suffix, tickers[:8], ["price", "info", "calendar", "dividends"] * 2, 8)
            if idle_seconds:
                clear_data()
                timeline.label = "idle"
                idle_started, request_offset = time.monotonic(), len(timeline.requests)
                while time.monotonic() - idle_started < idle_seconds:
                    remaining = idle_seconds - (time.monotonic() - idle_started)
                    time.sleep(min(10, max(0, remaining)))
                    print(f"idle_seconds={time.monotonic() - idle_started:.1f}", flush=True)
                report["idle_observation"] = {"seconds": time.monotonic() - idle_started,
                                              "business_requests": len(timeline.requests) - request_offset if instrumented else None}
                phase("price_after_idle", tickers[2:3], ["price"], 1)
            for level in (logging.ERROR, logging.CRITICAL):
                timeline.label = "independent_client"
                started = time.monotonic()
                client = DuckDBClient(log_level=level, config=configuration)
                client.connection.execute("SET enable_external_file_cache = false")
                clients.append(client)
                path = client._dataset_fs.register(first.huggingface_client.get_url_path("stock_prices"))
                client._load_or_build_parquet_index(first.huggingface_client.get_url_path("stock_prices"), path)
                report["phases"].append({"name": "independent_client",
                                         "wall_seconds": time.monotonic() - started})
                write_report(output, report)
            report["status"] = "complete"
        except BaseException as exc:
            report.update(status="failed", error_type=type(exc).__name__)
            raise
        finally:
            for client in clients:
                client.close()
            write_report(output, report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--capacity", type=int)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--sequential-samples", type=int, default=0)
    parser.add_argument("--idle-seconds", type=float, default=0)
    parser.add_argument("--no-trace", action="store_true")
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 2, 4, 8, 16, 32])
    args = parser.parse_args()
    if args.capacity is not None and args.capacity < 1:
        parser.error("capacity must be positive")
    if any(value < 1 or value > len(SYMBOLS) for value in args.concurrency):
        parser.error("concurrency must be between 1 and 32")
    if args.repeats < 1 or args.sequential_samples < 0 or args.sequential_samples > len(SYMBOLS) or args.idle_seconds < 0:
        parser.error("repeats must be positive; sequential samples 0..32; idle seconds nonnegative")
    run(args.output, args.baseline, args.capacity, args.concurrency, args.repeats,
        args.sequential_samples, args.idle_seconds, not args.no_trace)
