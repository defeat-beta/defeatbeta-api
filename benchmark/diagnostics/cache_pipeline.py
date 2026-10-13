"""Measure optional diagnostic overhead on a controlled local HTTP/2 cache path.

The peer runs in the same process. Results validate attribution and measure
instrumentation cost; they do not measure CDN performance or physical bandwidth.
"""

import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import ssl
import tempfile
from unittest.mock import patch

import httpx

from benchmark.diagnostics.cache_timeline import CacheTimeline
from benchmark.workloads.http_pool_defaults import measure
from defeatbeta_api.client.dataset_cache_fs import DatasetCacheFileSystem
from defeatbeta_api.client.http_pool import ConnectionManager, ManagedHTTPTransport
from test.http2_peer import http2_peer


PINNED = "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/resolve/diagnostic/data/US/stock_prices.parquet"


def run(args):
    mode = getattr(args, "receive_mode", "coordinated")
    context = (patch("defeatbeta_api.client.http_pool.coordinate_receives", return_value=None)
               if mode == "upstream" else nullcontext())
    with context:
        return _run(args)


def _run(args):
    if args.output.exists():
        raise FileExistsError("Diagnostic output already exists")
    report = {"status": "running", "created_at": datetime.now(timezone.utc).isoformat(),
              "methodology": {
                  "network": "Verified TLS HTTP/2 on loopback; no external network requests",
                  "peer": "Same-process test server; CPU includes client and peer",
                  "comparison": "Fixed receive mode per run; reverse hook order each round when both are selected",
                  "scope": "Cache range pipeline, not Ticker/DuckDB or physical bandwidth",
                  "receive_mode": getattr(args, "receive_mode", "coordinated"),
                  "hooks": getattr(args, "hooks", "both"),
                  "preparation": "Untimed workload establishes connections; clear only data blocks before batches",
                  "range_bytes": args.range_bytes, "tasks": args.tasks,
                  "rounds": args.rounds, "workers": args.workers,
                  "payload": "Deterministic bytes, verified outside timed work",
                  "timing": "Batch includes thread startup and cache writes; spans overlap",
              }, "sources": {}, "cases": []}
    for name in ("defeatbeta_api/client/http_pool.py", "defeatbeta_api/client/http_runtime.py",
                 "defeatbeta_api/client/http2_receive.py",
                 "defeatbeta_api/client/dataset_cache_fs.py", "benchmark/diagnostics/cache_pipeline.py",
                 "benchmark/diagnostics/cache_timeline.py", "benchmark/diagnostics/connection_timeline.py",
                 "benchmark/workloads/http_pool_defaults.py", "benchmark/workloads/http_pool_mixed.py", "test/http2_peer.py"):
        report["sources"][name] = hashlib.sha256(Path(name).read_bytes()).hexdigest()
    size = args.range_bytes * args.tasks
    payload = (bytes(range(256)) * ((size + 255) // 256))[:size]

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n")

    try:
        with http2_peer(payload=payload, max_concurrent_streams=100) as (url, certificate, peer):
            for workers in args.workers:
                manager = ConnectionManager()
                transport = ManagedHTTPTransport(http2=True, manager=manager,
                    verify=ssl.create_default_context(cafile=certificate))
                with httpx.Client(transport=transport, trust_env=False) as client, tempfile.TemporaryDirectory() as directory:
                    fs = DatasetCacheFileSystem(directory, "pipeline-v1",
                        lambda original, refresh=False: (url, size), http_client=client, workers=workers)
                    try:
                        path = fs.register(PINNED)

                        def fetch(index, timeline=None):
                            context = timeline.query(index=index) if timeline is not None else nullcontext()
                            with context:
                                return {"payload": fs.cat_file(path, index * args.range_bytes,
                                                               (index + 1) * args.range_bytes)}

                        warmup = measure(fetch, args.tasks, manager.snapshot)
                        if warmup["failed_requests"] or fs.await_pending()["errors"]:
                            raise RuntimeError("Local warmup failed")
                        for round_number in range(1, args.rounds + 1):
                            modes = (False, True) if round_number % 2 else (True, False)
                            if getattr(args, "hooks", "both") != "both":
                                modes = (args.hooks == "on",)
                            for detailed in modes:
                                with fs._guard:
                                    fs._memory_blocks.clear()
                                    fs._memory_access_ns.clear()
                                for block in Path(directory).glob("*.block"):
                                    block.unlink()
                                timeline = CacheTimeline() if detailed else None
                                hooks = timeline.installed(filesystems=[fs]) if timeline else nullcontext()
                                before = fs.metrics()["downloaded_bytes"]
                                with hooks:
                                    case = measure(lambda index: fetch(index, timeline), args.tasks, manager.snapshot)
                                    if fs.await_pending()["errors"]:
                                        raise RuntimeError("Pending local downloads failed")
                                for index, result in enumerate(case["results"]):
                                    actual = result.pop("payload", None)
                                    if actual != payload[index * args.range_bytes:(index + 1) * args.range_bytes]:
                                        raise ValueError("Local payload changed or query failed")
                                downloaded = fs.metrics()["downloaded_bytes"] - before
                                if downloaded != size:
                                    raise ValueError("Unexpected local byte workload")
                                case.update(round=round_number, workers=workers, detailed=detailed,
                                            downloaded_bytes=downloaded)
                                if timeline:
                                    case["pipeline"] = timeline.artifact()
                                report["cases"].append(case)
                                save()
                                print(f"workers={workers} round={round_number} detailed={detailed} "
                                      f"wall={case['wall_seconds']:.4f} cpu={case['cpu_seconds']:.4f} "
                                      f"p95={case['p95_seconds']:.4f} new={case['new_connections']} "
                                      f"failed={case['failed_requests']}", flush=True)
                    finally:
                        fs.close()
        report["status"] = "complete"
    except BaseException as exc:
        report.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        save()
    return report


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, nargs="+", default=[1, 16])
    parser.add_argument("--tasks", type=int, default=32)
    parser.add_argument("--range-bytes", type=int, default=131072)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--receive-mode", choices=["coordinated", "upstream"], default="coordinated")
    parser.add_argument("--hooks", choices=["off", "on", "both"], default="both")
    args = parser.parse_args()
    if min(args.tasks, args.range_bytes, args.rounds, *args.workers) <= 0:
        parser.error("Workload sizes and rounds must be positive")
    return args


if __name__ == "__main__":
    run(parse_args())
