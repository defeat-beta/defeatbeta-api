"""Relate process HTTP pool policy to real Range and Ticker concurrency.

Candidates run sequentially, in alternating order across rounds, on the same
dataset and workload. Reports contain no signed URLs or proxy credentials.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import statistics
import tempfile
from threading import Barrier, Event, Thread
import time
from urllib.parse import urlsplit

import psutil

from benchmark.common import SYMBOLS, percentile


def save(path, report):
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n")


def measure(fetch, concurrency, status):
    process = psutil.Process()
    rss_before = process.memory_info().rss
    cpu_before = process.cpu_times()
    stop = Event()
    observed = {"peak_connections": 0, "peak_reserved_streams": 0, "peak_pending_requests": 0,
                "limits": {}, "connection_ids": set(), "peak_rss_bytes": rss_before,
                "peak_connections_per_origin": {}}

    def sample():
        state = status()
        observed["peak_rss_bytes"] = max(observed["peak_rss_bytes"], process.memory_info().rss)
        origins = {}
        for connection in state["connections"]:
            origins[connection["origin"]] = origins.get(connection["origin"], 0) + 1
        for origin, count in origins.items():
            observed["peak_connections_per_origin"][origin] = max(
                observed["peak_connections_per_origin"].get(origin, 0), count)
        observed["peak_connections"] = max(observed["peak_connections"], len(state["connections"]))
        observed["peak_reserved_streams"] = max(observed["peak_reserved_streams"],
                                               sum(c["reserved_streams"] for c in state["connections"]))
        observed["peak_pending_requests"] = max(observed["peak_pending_requests"], state["pending_requests"])
        for connection in state["connections"]:
            if connection["reserved_streams"]:
                observed["connection_ids"].add(connection["connection_id"])
                observed["limits"][connection["origin"]] = {
                    "peer": connection["peer_stream_limit"], "effective": connection["effective_stream_limit"]}

    def monitor():
        while not stop.wait(0.005):
            sample()

    barrier = Barrier(concurrency)

    def query(index):
        barrier.wait(timeout=30)
        started = time.monotonic()
        try:
            result = fetch(index)
        except Exception as exc:
            result = {"error_type": type(exc).__name__}
        return {"seconds": time.monotonic() - started, **result}

    before = status()
    sample()
    thread = Thread(target=monitor, daemon=True)
    thread.start()
    started = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            results = list(executor.map(query, range(concurrency)))
        elapsed = time.monotonic() - started
    finally:
        stop.set()
        thread.join(timeout=3)
    sample()
    after = status()
    durations = [item["seconds"] for item in results]
    cpu_after = process.cpu_times()
    observed["connection_ids"] = sorted(observed["connection_ids"])
    return {"concurrency": concurrency, "wall_seconds": elapsed, "samples": len(results),
            "failed_requests": sum("error_type" in item for item in results),
            "rss_before_bytes": rss_before,
            "cpu_seconds": cpu_after.user + cpu_after.system - cpu_before.user - cpu_before.system,
            "p50_seconds": statistics.median(durations), "p95_seconds": percentile(durations, 0.95),
            "new_connections": after["created_connections"] - before["created_connections"],
            "pool_wait_seconds": after["pool_wait_seconds"] - before["pool_wait_seconds"],
            "assignments": after["assignments"] - before["assignments"],
            "allocator_dispatches": after.get("dispatches", 0) - before.get("dispatches", 0),
            "connection_close_errors": after.get("close_errors", 0) - before.get("close_errors", 0),
            "results": results, **observed}


def run(args):
    from defeatbeta_api.client.duckdb_conf import Configuration
    from defeatbeta_api.client.http_pool import configure_connection_pool, get_connection_pool_status
    from defeatbeta_api.client.hugging_face_client import HuggingFaceClient
    from defeatbeta_api.client.shared_resources import SharedHttpClient, close_network_resources
    from defeatbeta_api.data.ticker import Ticker
    from benchmark.common import result_fingerprint

    if args.output.exists():
        raise FileExistsError("Benchmark output already exists")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {"status": "running", "created_at": datetime.now(timezone.utc).isoformat(),
              "methodology": {
                  "network": args.network_label,
                  "routing": "Existing proxy and TLS environment; no proxy changes",
                  "scope": "Current network and dataset; application throughput, not wire bandwidth",
                  "order": "Sequential candidates; reverse candidate and concurrency order on alternate rounds",
                  "cache": "Footer/index prepared; data extents cleared before cold prices; DuckDB file cache disabled",
                  "pool": "Fresh pool per candidate/round; sequential warmup before measured batches",
                  "range_bytes": args.range_bytes, "rounds": args.rounds,
                  "percentiles": "Empirical nearest-rank P95; batch observations are correlated",
                  "sampler": "Pool state sampled every 5 ms; short-lived peaks may be missed",
              }, "sources": {}, "cases": []}
    for name in ("http_pool", "http_runtime", "shared_resources", "dataset_cache_fs", "duckdb_client", "duckdb_conf"):
        source = Path(f"defeatbeta_api/client/{name}.py")
        report["sources"][name] = hashlib.sha256(source.read_bytes()).hexdigest()
    policies = args.policies or [(core, workers, args.stream_limit) for core in args.cores for workers in args.fetch_workers]
    metadata = HuggingFaceClient()
    version = metadata.get_data_update_time()
    report["dataset_version"] = version
    signed, size = metadata.resolve_cdn_info(metadata.get_url_path("stock_prices"))
    report["range_origin"] = urlsplit(signed).netloc
    if size is None or size < 64 * args.range_bytes:
        raise ValueError("The price file is too small for the fixed Range workload")
    expected = {}
    try:
        for round_number in range(args.rounds):
            order = policies if round_number % 2 == 0 else list(reversed(policies))
            concurrencies = args.concurrency if round_number % 2 == 0 else list(reversed(args.concurrency))
            for core, workers, stream_limit in order:
                close_network_resources()
                configure_connection_pool(core_connections_per_origin=core,
                                          max_connections_for_all_origins=args.max_connections,
                                          max_streams_per_connection=stream_limit)
                with tempfile.TemporaryDirectory() as directory:
                    clients = []
                    configuration = Configuration(cache_directory=directory, cache_fetch_workers=workers,
                                                  cache_version_check_interval_seconds=86400)
                    raw = SharedHttpClient(timeout=30)
                    try:
                        tickers = []
                        if args.workload in ("price", "both"):
                            tickers = [Ticker(symbol, config=configuration, log_level=logging.WARNING)
                                       for symbol in SYMBOLS]
                            client = tickers[0].duckdb_client
                            clients.append(client)
                            if client._data_update_time != version:
                                raise ValueError("Dataset version changed during the benchmark")
                            client.connection.execute("SET enable_external_file_cache = false")
                            tickers[0].price()
                        if args.workload in ("range", "both"):
                            raw.get(signed, headers={"Range": "bytes=0-0", "Accept-Encoding": "identity"})

                        def clear_data():
                            for client in clients:
                                filesystem = client._dataset_fs
                                filesystem.await_pending()
                                with filesystem._guard:
                                    filesystem._memory_blocks.clear()
                                    filesystem._memory_access_ns.clear()
                            for path in Path(directory).glob("*.block"):
                                path.unlink()

                        def range_query(index):
                            start = (32 + index) * args.range_bytes
                            response = raw.get(signed, headers={"Range": f"bytes={start}-{start + args.range_bytes - 1}",
                                                                "Accept-Encoding": "identity"})
                            if response.status_code != 206 or len(response.content) != args.range_bytes:
                                raise ValueError("Range response did not match the requested extent")
                            return {"bytes": len(response.content), "sha256": hashlib.sha256(response.content).hexdigest()}

                        def price_query(index):
                            frame = tickers[index].price()
                            return {"symbol": tickers[index].ticker, "fingerprint": result_fingerprint(frame)}

                        for concurrency in concurrencies:
                            workloads = [("range", range_query)] if args.workload == "range" else [("price", price_query)]
                            if args.workload == "both":
                                workloads = [("range", range_query), ("price", price_query)]
                            for workload, query in workloads:
                                clear_data()
                                downloaded = sum(c._dataset_fs.metrics()["downloaded_bytes"] for c in clients)
                                case = measure(query, concurrency, get_connection_pool_status)
                                drain_started = time.monotonic()
                                for client in clients:
                                    client._dataset_fs.await_pending()
                                drain = time.monotonic() - drain_started
                                count = (sum(item.get("bytes", 0) for item in case["results"]) if workload == "range"
                                         else sum(c._dataset_fs.metrics()["downloaded_bytes"] for c in clients) - downloaded)
                                case.update(workload=workload, round=round_number + 1, core=core,
                                            max_connections=args.max_connections, stream_limit=stream_limit,
                                            fetch_workers=workers, downloaded_bytes=count,
                                            prefetch_drain_seconds=drain, bytes_per_second=count / (case["wall_seconds"] + drain))
                                for index, result in enumerate(case["results"]):
                                    if "error_type" in result:
                                        continue
                                    key = (workload, index)
                                    fingerprint = result.get("fingerprint", result.get("sha256"))
                                    if key in expected and expected[key] != fingerprint:
                                        raise ValueError("Result fingerprint changed across pool policies")
                                    expected[key] = fingerprint
                                report["cases"].append(case)
                                save(args.output, report)
                                print(f"round={round_number + 1} core={core} fetch_workers={workers} streams_per_connection={stream_limit} "
                                      f"workload={workload} concurrency={concurrency} p50={case['p50_seconds']:.3f} "
                                      f"p95={case['p95_seconds']:.3f} connections={case['peak_connections']} "
                                      f"streams={case['peak_reserved_streams']} pending={case['peak_pending_requests']} "
                                      f"failed={case['failed_requests']}", flush=True)
                    finally:
                        for client in clients:
                            client.close()
                        close_network_resources()
        report["status"] = "complete_with_errors" if any(c["failed_requests"] for c in report["cases"]) else "complete"
    except BaseException as exc:
        report.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        metadata.session.close()
        close_network_resources()
        save(args.output, report)


def parse_policy(value):
    try:
        core, workers, limit = value.split(":")
        return int(core), int(workers), None if limit == "peer" else int(limit)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError("Policy must be core:workers:streams, with peer for no extra stream ceiling") from exc


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--network-label", default="Unspecified network")
    parser.add_argument("--cores", type=int, nargs="+", default=[1, 2, 4])
    parser.add_argument("--max-connections", type=int, default=16)
    parser.add_argument("--stream-limit", type=int)
    parser.add_argument("--policies", type=parse_policy, nargs="+")
    parser.add_argument("--fetch-workers", type=int, nargs="+", default=[3])
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 8, 16, 32])
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--range-bytes", type=int, default=256 * 1024)
    parser.add_argument("--workload", choices=["range", "price", "both"], default="both")
    args = parser.parse_args()
    if args.policies and any(core < 1 or core > args.max_connections or workers < 1
                             or limit is not None and limit < 1 for core, workers, limit in args.policies):
        parser.error("Invalid policy connection count, worker count, or stream limit")
    if (args.rounds < 1 or any(n < 1 or n > len(SYMBOLS) for n in args.concurrency)
            or any(n < 1 for n in args.fetch_workers) or args.range_bytes < 1
            or any(n < 1 or n > args.max_connections for n in args.cores)):
        parser.error("Invalid concurrency, connection budget, worker count, range size, or rounds")
    run(args)
