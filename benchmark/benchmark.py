"""End-to-end DefeatBeta API benchmark and immutable result archive CLI."""

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import AsyncExitStack, contextmanager
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
from threading import Lock
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
from urllib.parse import urlsplit
import uuid


WORKER_ENTRY_NS = time.perf_counter_ns()
ROOT = Path(__file__).resolve().parent
DEFAULT_SYMBOLS = ("AAPL", "KDP", "ZTS")
DEFAULT_RUNS = 3
DEFAULT_TIMEOUT = 600.0
RESULT_MARKER = "BENCH_RESULT="
PRIMARY_METRIC = "execute_query_seconds"
STOCK_PRICES_URL = (
    "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/"
    "resolve/main/data/US/stock_prices.parquet"
)

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


def httpx_proxy_options(proxy):
    """Use the environment unless an explicit transport route was requested."""
    return {"proxy": proxy or None, "trust_env": proxy is None}


def network_range_plan(file_size, block_size):
    """Select distinct cache-sized blocks used by the stock price query."""
    if file_size <= 0 or block_size <= 0:
        raise ValueError("file size and block size must be positive")
    plan = []
    for index in range(min(2, (file_size + block_size - 1) // block_size)):
        start = index * block_size
        plan.append((f"front_{index}", start, min(start + block_size, file_size) - 1))
    tail_start = ((file_size - 1) // block_size) * block_size
    if tail_start >= 2 * block_size:
        plan.append(("tail", tail_start, file_size - 1))
    return plan


def causal_control_plan(file_size, block_size, first_block, reference):
    """Create disjoint control ranges with the reference transfer lengths."""
    plan = []
    for index, (_, reference_start, reference_end) in enumerate(reference):
        start = (first_block + index) * block_size
        end = start + reference_end - reference_start
        if end >= file_size:
            raise ValueError("file is too small for the selected control ranges")
        plan.append((f"control_{first_block}_{index}", start, end))
    return plan


def parse_content_range(value):
    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", value or "")
    if match is None:
        raise ValueError("invalid Content-Range")
    start, end, total = map(int, match.groups())
    if total <= 0 or start > end or end >= total:
        raise ValueError("invalid Content-Range bounds")
    return start, end, total


def validate_range_response(status, content_range, length, start, end, total, encoding):
    if status != 206:
        raise ValueError(f"expected HTTP 206, received {status}")
    if parse_content_range(content_range) != (start, end, total):
        raise ValueError("unexpected Content-Range")
    if encoding not in (None, "identity"):
        raise ValueError("unexpected content encoding")
    if length != end - start + 1:
        raise ValueError("unexpected response length")


async def _probe_range(
    client, url, name, start, end, total, sample_started_ns, include_body=False
):
    request_started_ns = time.perf_counter_ns()
    first_body_ns = None
    length = 0
    digest = hashlib.sha256()
    body = bytearray() if include_body else None
    headers = {"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"}
    async with client.stream("GET", url, headers=headers) as response:
        headers_received_ns = time.perf_counter_ns()
        status = response.status_code
        content_range = response.headers.get("Content-Range")
        encoding = response.headers.get("Content-Encoding")
        http_version = response.http_version
        try:
            network_stream = response.extensions["network_stream"]
            local_port = network_stream.get_extra_info("socket").getsockname()[1]
        except (AttributeError, KeyError, OSError, TypeError):
            local_port = None
        async for chunk in response.aiter_raw():
            if first_body_ns is None:
                first_body_ns = time.perf_counter_ns()
            length += len(chunk)
            digest.update(chunk)
            if body is not None:
                body.extend(chunk)
    finished_ns = time.perf_counter_ns()
    validate_range_response(status, content_range, length, start, end, total, encoding)
    result = {
        "name": name,
        "start": start,
        "end": end,
        "bytes": length,
        "sha256": digest.hexdigest(),
        "http_version": http_version,
        "local_port": local_port,
        "request_start_seconds": (request_started_ns - sample_started_ns) / 1e9,
        "headers_seconds": (headers_received_ns - sample_started_ns) / 1e9,
        "first_body_seconds": (
            (first_body_ns - sample_started_ns) / 1e9
            if first_body_ns is not None else None
        ),
        "finish_seconds": (finished_ns - sample_started_ns) / 1e9,
    }
    if body is not None:
        result["body"] = bytes(body)
    return result


async def resolve_signed_url(client, url):
    response = await client.head(url, follow_redirects=False)
    if response.status_code not in (301, 302, 303, 307, 308):
        raise ValueError(f"resolve HEAD returned HTTP {response.status_code}")
    location = response.headers.get("Location")
    parts = urlsplit(location or "")
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("resolve HEAD returned an unsafe Location")
    return location


async def run_network_probe(url, proxy, runs, timeout, block_size):
    """Measure warmed, uncached Range transfers without changing the API cache."""
    try:
        import httpx
        import h2  # noqa: F401 - required by httpx HTTP/2 support
    except ImportError as exc:
        raise RuntimeError("install the optional httpx[http2] benchmark dependency") from exc

    limits = httpx.Limits(max_connections=3, max_keepalive_connections=3, keepalive_expiry=120)
    async with httpx.AsyncClient(
        http2=True, timeout=timeout, limits=limits, **httpx_proxy_options(proxy)
    ) as client:
        resolve_started_ns = time.perf_counter_ns()
        signed_url = await resolve_signed_url(client, url)
        resolve_seconds = (time.perf_counter_ns() - resolve_started_ns) / 1e9
        warm_started_ns = time.perf_counter_ns()
        warm = await client.get(
            signed_url,
            headers={"Range": "bytes=0-0", "Accept-Encoding": "identity"},
        )
        warm_seconds = (time.perf_counter_ns() - warm_started_ns) / 1e9
        _, _, file_size = parse_content_range(warm.headers.get("Content-Range"))
        validate_range_response(
            warm.status_code, warm.headers.get("Content-Range"), len(warm.content),
            0, 0, file_size, warm.headers.get("Content-Encoding"),
        )
        plan = network_range_plan(file_size, block_size)
        samples = []
        expected_digests = None
        for trial in range(1, runs + 1):
            sample_started_ns = time.perf_counter_ns()
            transfers = await asyncio.gather(*(
                _probe_range(client, signed_url, name, start, end, file_size, sample_started_ns)
                for name, start, end in plan
            ))
            wall_seconds = (time.perf_counter_ns() - sample_started_ns) / 1e9
            digests = {item["name"]: item["sha256"] for item in transfers}
            if expected_digests is not None and digests != expected_digests:
                raise ValueError("Range content changed between trials")
            expected_digests = digests
            samples.append({
                "trial": trial,
                "wall_seconds": wall_seconds,
                "bytes": sum(item["bytes"] for item in transfers),
                "transfers": transfers,
            })
    return {
        "probe": "warm_connection_parallel_range_get",
        "url": url,
        "cdn_host": urlsplit(signed_url).hostname,
        "proxy": redact_proxy(proxy),
        "resolve_seconds": resolve_seconds,
        "warmup_seconds": warm_seconds,
        "warmup_http_version": warm.http_version,
        "file_size": file_size,
        "block_size": block_size,
        "ranges": [{"name": name, "start": start, "end": end} for name, start, end in plan],
        "runs": runs,
        "median_wall_seconds": statistics.median(item["wall_seconds"] for item in samples),
        "samples": samples,
        "limitations": (
            "Network-only diagnostic; it excludes DuckDB, cache_httpfs, Parquet decoding, "
            "and DataFrame materialization. The first byte of the file is fetched only "
            "to warm the connection and is not stored in a local data cache."
        ),
    }


async def run_network_causality_probe(
    url, proxy, timeout, block_size, new_warmup_bytes=1, idle_seconds=0.0
):
    """Cross connection age with previously requested and new byte ranges."""
    try:
        import httpx
        import h2  # noqa: F401 - required by httpx HTTP/2 support
    except ImportError as exc:
        raise RuntimeError("install the optional httpx[http2] benchmark dependency") from exc

    limits = httpx.Limits(max_connections=3, max_keepalive_connections=3, keepalive_expiry=120)

    def new_client():
        return httpx.AsyncClient(
            http2=True, timeout=timeout, limits=limits, **httpx_proxy_options(proxy)
        )

    async def measure_stage(client, signed_url, label, plan, file_size):
        started_ns = time.perf_counter_ns()
        transfers = await asyncio.gather(*(
            _probe_range(client, signed_url, name, start, end, file_size, started_ns)
            for name, start, end in plan
        ))
        return {
            "label": label,
            "wall_seconds": (time.perf_counter_ns() - started_ns) / 1e9,
            "bytes": sum(item["bytes"] for item in transfers),
            "transfers": transfers,
        }

    async with new_client() as old_client:
        signed_url = await resolve_signed_url(old_client, url)
        warm = await old_client.get(
            signed_url,
            headers={"Range": "bytes=0-0", "Accept-Encoding": "identity"},
        )
        _, _, file_size = parse_content_range(warm.headers.get("Content-Range"))
        validate_range_response(
            warm.status_code, warm.headers.get("Content-Range"), len(warm.content),
            0, 0, file_size, warm.headers.get("Content-Encoding"),
        )
        reference = network_range_plan(file_size, block_size)
        if len(reference) != 3:
            raise ValueError("file is too small for three-range causality probe")
        control_b = causal_control_plan(file_size, block_size, 8, reference)
        control_c = causal_control_plan(file_size, block_size, 16, reference)
        neutral_offset = 24 * block_size
        neutral_end = neutral_offset + new_warmup_bytes - 1
        if neutral_end >= file_size:
            raise ValueError("file is too small for a neutral connection warmup")
        stages = [
            await measure_stage(old_client, signed_url, "old_connection_first_ranges", reference, file_size)
        ]
        idle_started_ns = time.perf_counter_ns()
        await asyncio.sleep(idle_seconds)
        actual_idle_seconds = (time.perf_counter_ns() - idle_started_ns) / 1e9
        stages.append(
            await measure_stage(old_client, signed_url, "old_connection_new_ranges", control_b, file_size)
        )
        async with new_client() as fresh_client:
            fresh_warm_started_ns = time.perf_counter_ns()
            fresh_warm = await fresh_client.get(
                signed_url,
                headers={
                    "Range": f"bytes={neutral_offset}-{neutral_end}",
                    "Accept-Encoding": "identity",
                },
            )
            fresh_warm_seconds = (time.perf_counter_ns() - fresh_warm_started_ns) / 1e9
            validate_range_response(
                fresh_warm.status_code, fresh_warm.headers.get("Content-Range"),
                len(fresh_warm.content), neutral_offset, neutral_end, file_size,
                fresh_warm.headers.get("Content-Encoding"),
            )
            stages.extend([
                await measure_stage(fresh_client, signed_url, "new_connection_repeated_ranges", reference, file_size),
                await measure_stage(fresh_client, signed_url, "new_connection_new_ranges", control_c, file_size),
            ])
    first_hashes = [item["sha256"] for item in stages[0]["transfers"]]
    repeat_hashes = [item["sha256"] for item in stages[2]["transfers"]]
    if first_hashes != repeat_hashes:
        raise ValueError("repeated Range content changed across connections")
    return {
        "probe": "range_connection_vs_remote_cache_causality",
        "url": url,
        "cdn_host": urlsplit(signed_url).hostname,
        "proxy": redact_proxy(proxy),
        "file_size": file_size,
        "block_size": block_size,
        "idle_seconds_requested": idle_seconds,
        "idle_seconds_actual": actual_idle_seconds,
        "new_connection_warmup_bytes": new_warmup_bytes,
        "new_connection_warmup_seconds": fresh_warm_seconds,
        "http_version": warm.http_version,
        "stages": stages,
        "limitations": (
            "All stages download complete response bodies without a local data cache. "
            "The proxy and CDN may cache ranges at an unknown granularity; this "
            "single-object crossover is diagnostic, not a proof of cache location."
        ),
    }


TRANSPORT_MODES = (
    "http2_multiplexed",
    "http2_independent",
    "http1_independent",
)


def transport_probe_schedule(runs):
    """Rotate mode order so time-varying network conditions affect each mode."""
    if runs < 1:
        raise ValueError("runs must be positive")
    return [
        (trial + 1, mode)
        for trial in range(runs)
        for mode in TRANSPORT_MODES[trial % len(TRANSPORT_MODES):]
        + TRANSPORT_MODES[:trial % len(TRANSPORT_MODES)]
    ]


def validate_transport_sample(mode, transfers):
    expected_version = "HTTP/1.1" if mode == "http1_independent" else "HTTP/2"
    if any(item["http_version"] != expected_version for item in transfers):
        raise ValueError(f"{mode} did not use {expected_version}")
    ports = [item["local_port"] for item in transfers]
    expected_ports = 1 if mode == "http2_multiplexed" else len(transfers)
    if None in ports or len(set(ports)) != expected_ports:
        raise ValueError(f"{mode} did not use {expected_ports} verifiable connections")


def transport_client_index(trial, range_index, client_count):
    return (range_index + trial - 1) % client_count


async def run_network_transport_probe(url, proxy, runs, timeout, block_size):
    """Compare multiplexing and independent warm connections for identical ranges."""
    try:
        import httpx
        import h2  # noqa: F401 - required by httpx HTTP/2 support
    except ImportError as exc:
        raise RuntimeError("install the optional httpx[http2] benchmark dependency") from exc

    schedule = transport_probe_schedule(runs)
    limits = httpx.Limits(max_connections=1, max_keepalive_connections=1, keepalive_expiry=120)

    def new_client(http2):
        return httpx.AsyncClient(
            http2=http2, timeout=timeout, limits=limits, **httpx_proxy_options(proxy)
        )

    async with new_client(True) as resolver:
        signed_url = await resolve_signed_url(resolver, url)
        size_response = await resolver.get(
            signed_url, headers={"Range": "bytes=0-0", "Accept-Encoding": "identity"}
        )
        _, _, file_size = parse_content_range(size_response.headers.get("Content-Range"))
        validate_range_response(
            size_response.status_code, size_response.headers.get("Content-Range"),
            len(size_response.content), 0, 0, file_size,
            size_response.headers.get("Content-Encoding"),
        )
    neutral_offset = 24 * block_size
    if neutral_offset >= file_size:
        raise ValueError("file is too small for the neutral warmup range")
    plan = network_range_plan(file_size, block_size)
    if len(plan) != 3:
        raise ValueError("file is too small for three-range transport probe")

    async with AsyncExitStack() as stack:
        clients = {
            mode: [
                await stack.enter_async_context(new_client(mode != "http1_independent"))
                for _ in range(1 if mode == "http2_multiplexed" else 3)
            ]
            for mode in TRANSPORT_MODES
        }
        warm_start = time.perf_counter_ns()
        warm_responses = await asyncio.gather(*(
            client.get(
                signed_url,
                headers={"Range": f"bytes={neutral_offset}-{neutral_offset}",
                         "Accept-Encoding": "identity"},
            )
            for group in clients.values() for client in group
        ))
        warm_seconds = (time.perf_counter_ns() - warm_start) / 1e9
        for response in warm_responses:
            validate_range_response(
                response.status_code, response.headers.get("Content-Range"),
                len(response.content), neutral_offset, neutral_offset,
                file_size, response.headers.get("Content-Encoding"),
            )
        samples = []
        expected_digests = None
        for trial, mode in schedule:
            started_ns = time.perf_counter_ns()
            group = clients[mode]
            transfers = await asyncio.gather(*(
                _probe_range(
                    group[transport_client_index(trial, index, len(group))],
                    signed_url, name, start, end,
                    file_size, started_ns,
                )
                for index, (name, start, end) in enumerate(plan)
            ))
            wall_seconds = (time.perf_counter_ns() - started_ns) / 1e9
            validate_transport_sample(mode, transfers)
            digests = {item["name"]: item["sha256"] for item in transfers}
            if expected_digests is not None and digests != expected_digests:
                raise ValueError("Range content changed between transport modes")
            expected_digests = digests
            samples.append({
                "trial": trial,
                "mode": mode,
                "wall_seconds": wall_seconds,
                "bytes": sum(item["bytes"] for item in transfers),
                "effective_mbps": sum(item["bytes"] for item in transfers) * 8 / wall_seconds / 1e6,
                "transfers": transfers,
            })
    return {
        "probe": "http_transport_concurrency_comparison",
        "url": url,
        "cdn_host": urlsplit(signed_url).hostname,
        "proxy": redact_proxy(proxy),
        "file_size": file_size,
        "block_size": block_size,
        "warmup_seconds": warm_seconds,
        "ranges": [{"name": name, "start": start, "end": end} for name, start, end in plan],
        "runs_per_mode": runs,
        "median_by_mode": {
            mode: statistics.median(
                item["wall_seconds"] for item in samples if item["mode"] == mode
            )
            for mode in TRANSPORT_MODES
        },
        "samples": samples,
        "limitations": (
            "Network-only diagnostic over one signed URL and identical ranges. "
            "Connections are warmed with one neutral byte, and no local data cache is used. "
            "It excludes DuckDB, cache_httpfs, Parquet decoding, and DataFrame materialization. "
            "The proxy or CDN may cache requested ranges between modes."
        ),
    }


def network_fanout_plan(file_size, block_size, chunk_size):
    """Split the query's exact remote byte ranges without changing total bytes."""
    if chunk_size < 1:
        raise ValueError("chunk size must be positive")
    chunks = []
    for name, start, end in network_range_plan(file_size, block_size):
        for part, offset in enumerate(range(start, end + 1, chunk_size)):
            chunks.append((f"{name}_part_{part}", offset, min(offset + chunk_size - 1, end)))
    return chunks


def fanout_probe_schedule(runs, modes):
    if runs < 1:
        raise ValueError("runs must be positive")
    return [
        (trial + 1, mode)
        for trial in range(runs)
        for mode in modes[trial % len(modes):] + modes[:trial % len(modes)]
    ]


def validate_fanout_connections(transfers, warm_ports, assigned_indices):
    if len(transfers) != len(assigned_indices) or None in warm_ports:
        raise ValueError("fanout sample cannot verify warm connections")
    if len(set(warm_ports)) != len(warm_ports):
        raise ValueError("fanout warm connections are not distinct")
    for item, index in zip(transfers, assigned_indices):
        if item["http_version"] != "HTTP/2" or item["local_port"] != warm_ports[index]:
            raise ValueError("fanout sample did not reuse the expected warm connection")
    if {item["local_port"] for item in transfers} != set(warm_ports):
        raise ValueError("fanout sample did not use every warm connection")


async def run_network_fanout_probe(url, proxy, runs, timeout, block_size):
    """Separate the effects of HTTP/2 connection count and Range chunk size."""
    try:
        import httpx
        import h2  # noqa: F401 - required by httpx HTTP/2 support
    except ImportError as exc:
        raise RuntimeError("install the optional httpx[http2] benchmark dependency") from exc

    limits = httpx.Limits(max_connections=1, max_keepalive_connections=1, keepalive_expiry=120)

    def new_client():
        return httpx.AsyncClient(
            http2=True, timeout=timeout, limits=limits, **httpx_proxy_options(proxy)
        )

    async with new_client() as resolver:
        signed_url = await resolve_signed_url(resolver, url)
        size_response = await resolver.get(
            signed_url, headers={"Range": "bytes=0-0", "Accept-Encoding": "identity"}
        )
        _, _, file_size = parse_content_range(size_response.headers.get("Content-Range"))
        validate_range_response(
            size_response.status_code, size_response.headers.get("Content-Range"),
            len(size_response.content), 0, 0, file_size,
            size_response.headers.get("Content-Encoding"),
        )
    neutral_offset = 24 * block_size
    if neutral_offset >= file_size:
        raise ValueError("file is too small for the neutral warmup range")
    if len(network_range_plan(file_size, block_size)) != 3:
        raise ValueError("file is too small for three-range fanout probe")

    plans = {
        size: network_fanout_plan(file_size, block_size, size)
        for size in (block_size, max(1, block_size // 2), max(1, block_size // 4))
    }
    modes = [
        (size, count)
        for size, plan in plans.items()
        for count in (3, 6, 12)
        if count <= len(plan)
    ]
    schedule = fanout_probe_schedule(runs, modes)
    async with AsyncExitStack() as stack:
        clients = {
            count: [await stack.enter_async_context(new_client()) for _ in range(count)]
            for count in (3, 6, 12)
        }
        warm_started_ns = time.perf_counter_ns()
        warm_ports = {}
        for count, group in clients.items():
            warm_results = await asyncio.gather(*(
                _probe_range(
                    client, signed_url, "warm", neutral_offset, neutral_offset,
                    file_size, warm_started_ns,
                )
                for client in group
            ))
            ports = [item["local_port"] for item in warm_results]
            if (any(item["http_version"] != "HTTP/2" for item in warm_results)
                    or None in ports or len(set(ports)) != count):
                raise ValueError("fanout warmup did not create distinct HTTP/2 connections")
            warm_ports[count] = ports
        warm_seconds = (time.perf_counter_ns() - warm_started_ns) / 1e9
        samples = []
        expected_sha256 = None
        for trial, (chunk_size, count) in schedule:
            plan = plans[chunk_size]
            group = clients[count]
            assigned_indices = [
                transport_client_index(trial, index, count)
                for index in range(len(plan))
            ]
            started_ns = time.perf_counter_ns()
            transfers = await asyncio.gather(*(
                _probe_range(
                    group[assigned_indices[index]],
                    signed_url, name, start, end, file_size, started_ns,
                    include_body=True,
                )
                for index, (name, start, end) in enumerate(plan)
            ))
            wall_seconds = (time.perf_counter_ns() - started_ns) / 1e9
            validate_fanout_connections(transfers, warm_ports[count], assigned_indices)
            digest = hashlib.sha256()
            for item in transfers:
                digest.update(item.pop("body"))
            payload_sha256 = digest.hexdigest()
            if expected_sha256 is not None and payload_sha256 != expected_sha256:
                raise ValueError("Range content changed between fanout modes")
            expected_sha256 = payload_sha256
            total_bytes = sum(item["bytes"] for item in transfers)
            samples.append({
                "trial": trial,
                "chunk_size": chunk_size,
                "connections": count,
                "requests": len(plan),
                "wall_seconds": wall_seconds,
                "bytes": total_bytes,
                "effective_mbps": total_bytes * 8 / wall_seconds / 1e6,
                "payload_sha256": payload_sha256,
                "transfers": transfers,
            })
    return {
        "probe": "http2_range_fanout_comparison",
        "url": url,
        "cdn_host": urlsplit(signed_url).hostname,
        "proxy": redact_proxy(proxy),
        "file_size": file_size,
        "block_size": block_size,
        "warmup_seconds": warm_seconds,
        "runs_per_mode": runs,
        "modes": [
            {"chunk_size": size, "connections": count, "requests": len(plans[size])}
            for size, count in modes
        ],
        "samples": samples,
        "limitations": (
            "Network-only diagnostic using the same exact remote bytes in every mode. "
            "One neutral byte is used to warm each connection; no local data cache is used. "
            "It excludes DuckDB, cache_httpfs, Parquet decoding, and DataFrame materialization. "
            "Shared proxy traffic and remote caches are uncontrolled."
        ),
    }


def make_range_probe_filesystem(client, signed_url, file_size, block_size):
    """Build an isolated read-through fsspec adapter for a DuckDB experiment."""
    try:
        import fsspec
    except ImportError as exc:
        raise RuntimeError("install the optional fsspec benchmark dependency") from exc

    class RangeProbeFileSystem(fsspec.AbstractFileSystem):
        protocol = "rangeprobe"
        root_marker = ""

        def __init__(self, **kwargs):
            super().__init__(skip_instance_cache=True, **kwargs)
            self.client = client
            self.signed_url = signed_url
            self.file_size = file_size
            self.block_size = block_size
            self.blocks = {}
            self.pending = {}
            self.transfer_events = []
            self.read_events = []
            self.lock = Lock()
            self.executor = ThreadPoolExecutor(max_workers=3)

        def info(self, path, **kwargs):
            return {"name": path, "size": self.file_size, "type": "file"}

        def ls(self, path, detail=True, **kwargs):
            entry = self.info(path)
            return [entry] if detail else [entry["name"]]

        def modified(self, path):
            return datetime.fromtimestamp(0, timezone.utc)

        def created(self, path):
            return self.modified(path)

        def _open(self, path, mode="rb", **kwargs):
            if mode != "rb":
                raise ValueError("range probe filesystem is read-only")
            return fsspec.spec.AbstractBufferedFile(
                self, path, mode=mode, block_size=self.block_size,
                cache_type="none", size=self.file_size,
            )

        def _download_block(self, start):
            import httpx

            end = min(start + self.block_size, self.file_size) - 1
            started_ns = time.perf_counter_ns()
            for attempt in range(2):
                try:
                    response = self.client.get(
                        self.signed_url,
                        headers={"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"},
                    )
                    break
                except httpx.TransportError:
                    if attempt == 1:
                        raise
            content = response.content
            validate_range_response(
                response.status_code, response.headers.get("Content-Range"),
                len(content), start, end, self.file_size,
                response.headers.get("Content-Encoding"),
            )
            with self.lock:
                self.transfer_events.append({
                    "start": start,
                    "bytes": len(content),
                    "seconds": (time.perf_counter_ns() - started_ns) / 1e9,
                    "http_version": response.http_version,
                })
            return content

        def _block(self, start):
            with self.lock:
                if start in self.blocks:
                    return self.blocks[start]
                future = self.pending.get(start)
                if future is None:
                    future = self.executor.submit(self._download_block, start)
                    self.pending[start] = future
            content = future.result()
            with self.lock:
                self.blocks[start] = content
            return content

        def prefetch(self):
            for _, start, _ in network_range_plan(self.file_size, self.block_size):
                with self.lock:
                    if start not in self.pending:
                        self.pending[start] = self.executor.submit(self._download_block, start)

        def cat_file(self, path, start=None, end=None, **kwargs):
            started_ns = time.perf_counter_ns()
            start = 0 if start is None else max(0, start)
            end = self.file_size if end is None else min(self.file_size, end)
            if end <= start:
                return b""
            pieces = []
            for offset in range((start // self.block_size) * self.block_size, end, self.block_size):
                block = self._block(offset)
                left = max(start - offset, 0)
                right = min(end - offset, len(block))
                pieces.append(block[left:right])
            content = b"".join(pieces)
            with self.lock:
                self.read_events.append({
                    "start": start,
                    "end": end,
                    "seconds": (time.perf_counter_ns() - started_ns) / 1e9,
                })
            return content

        def close(self):
            self.executor.shutdown(wait=True)

    return RangeProbeFileSystem()


def run_fsspec_probe(proxy, runs, timeout, block_size):
    """Measure Ticker.price through an isolated speculative fsspec adapter."""
    try:
        import duckdb
        import httpx
        import h2  # noqa: F401 - required by httpx HTTP/2 support
    except ImportError as exc:
        raise RuntimeError("install duckdb, fsspec, and httpx[http2] to run this probe") from exc

    sys.path.insert(0, str(ROOT.parent))
    api = load_api_bindings()
    from defeatbeta_api.utils.const import stock_prices

    client = httpx.Client(
        http2=True, timeout=timeout, **httpx_proxy_options(proxy),
        limits=httpx.Limits(max_connections=3, max_keepalive_connections=3, keepalive_expiry=120),
    )
    try:
        resolve_started_ns = time.perf_counter_ns()
        resolved = client.head(STOCK_PRICES_URL, follow_redirects=False)
        signed_url = resolved.headers.get("Location")
        parts = urlsplit(signed_url or "")
        if resolved.status_code not in (301, 302, 303, 307, 308):
            raise ValueError(f"resolve HEAD returned HTTP {resolved.status_code}")
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise ValueError("resolve HEAD returned an unsafe Location")
        resolve_seconds = (time.perf_counter_ns() - resolve_started_ns) / 1e9
        warm_started_ns = time.perf_counter_ns()
        warm = client.get(
            signed_url, headers={"Range": "bytes=0-0", "Accept-Encoding": "identity"}
        )
        warm_seconds = (time.perf_counter_ns() - warm_started_ns) / 1e9
        _, _, file_size = parse_content_range(warm.headers.get("Content-Range"))
        validate_range_response(
            warm.status_code, warm.headers.get("Content-Range"), len(warm.content),
            0, 0, file_size, warm.headers.get("Content-Encoding"),
        )
        samples = []
        expected_result = None
        for trial in range(1, runs + 1):
            with tempfile.TemporaryDirectory(prefix="defeatbeta-fsspec-probe-") as directory:
                cache = Path(directory) / "http-cache"
                cache.mkdir()
                config = api.Configuration(
                    cache_httpfs_cache_directory=str(cache), resolve_direct=False
                )
                ticker = api.Ticker(
                    "AAPL", http_proxy=proxy, log_level=logging.WARNING, config=config
                )
                filesystem = make_range_probe_filesystem(client, signed_url, file_size, block_size)
                try:
                    connection = ticker.duckdb_client.connection
                    connection.register_filesystem(filesystem)
                    cache_status_before = _frame_records(
                        connection, "SELECT * FROM cache_httpfs_cache_status_query()"
                    )
                    validate_cold_cache_status(cache_status_before)
                    original_get_url_path = ticker.huggingface_client.get_url_path
                    ticker.huggingface_client.get_url_path = lambda table: (
                        "rangeprobe://stock_prices.parquet"
                        if table == stock_prices else original_get_url_path(table)
                    )
                    original_execute = ticker.duckdb_client._execute_query
                    wrapped_timing = {}

                    def execute_with_prefetch(sql):
                        started_ns = time.perf_counter_ns()
                        filesystem.prefetch()
                        result_frame = original_execute(sql)
                        wrapped_timing["seconds"] = (
                            time.perf_counter_ns() - started_ns
                        ) / 1e9
                        return result_frame

                    ticker.duckdb_client._execute_query = execute_with_prefetch
                    events = []
                    cpu_before = resource.getrusage(resource.RUSAGE_SELF)
                    api_started_ns = time.perf_counter_ns()
                    with api.capture_performance(events.append):
                        frame = ticker.price()
                    api_seconds = (time.perf_counter_ns() - api_started_ns) / 1e9
                    cpu_after = resource.getrusage(resource.RUSAGE_SELF)
                    result = result_fingerprint(frame)
                    if expected_result is not None and result != expected_result:
                        raise ValueError("Ticker.price result changed between trials")
                    expected_result = result
                    phases = _event_totals(events)
                    samples.append({
                        "trial": trial,
                        "query_seconds": wrapped_timing["seconds"],
                        "execute_query_seconds": phases["duckdb.execute_query"]["seconds"],
                        "api_call_seconds": api_seconds,
                        "performance": phases,
                        "cpu_user_seconds": cpu_after.ru_utime - cpu_before.ru_utime,
                        "cpu_system_seconds": cpu_after.ru_stime - cpu_before.ru_stime,
                        "cache_status_before_query": cache_status_before,
                        "cache_after_query": cache_snapshot(cache),
                        "cached_blocks": len(filesystem.blocks),
                        "cached_bytes": sum(map(len, filesystem.blocks.values())),
                        "transfer_events": sorted(
                            filesystem.transfer_events, key=lambda item: item["start"]
                        ),
                        "read_events": filesystem.read_events,
                        "result": result,
                    })
                finally:
                    ticker.duckdb_client.close()
                    filesystem.close()
    finally:
        client.close()
    return {
        "probe": "ticker_price_fsspec_parallel_range_prototype",
        "proxy": redact_proxy(proxy),
        "resolve_seconds": resolve_seconds,
        "warmup_seconds": warm_seconds,
        "warmup_http_version": warm.http_version,
        "file_size": file_size,
        "block_size": block_size,
        "samples": samples,
        "median_query_seconds": statistics.median(item["query_seconds"] for item in samples),
        "limitations": (
            "Real Ticker.price and DuckDBClient._execute_query with a benchmark-only "
            "URL substitution and fsspec adapter. This is not shipped API behavior. "
            "Each trial uses a new empty local data cache and a shared warmed HTTP client."
        ),
    }


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


def select_cache_profile(parent_profile, cursor_diagnostics):
    for entry in reversed(cursor_diagnostics or []):
        if isinstance(entry.get("cache_profile"), list):
            return entry["cache_profile"], "query_cursor"
    return parent_profile, "parent_connection"


def collect_diagnostics(ticker, cache_profile, http_events=None, cursor_diagnostics=None):
    connection = ticker.duckdb_client.connection
    selected_profile, profile_scope = select_cache_profile(
        cache_profile, cursor_diagnostics
    )
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
        "cache_profile": selected_profile,
        "cache_profile_scope": profile_scope,
        "http_events": http_events or [],
        "cursor_diagnostics": cursor_diagnostics or [],
        "loaded_extensions": _frame_records(
            connection,
            "SELECT extension_name, extension_version FROM duckdb_extensions() "
            "WHERE loaded ORDER BY extension_name",
        ),
    }


def sanitize_http_event(row):
    """Keep request timing and numeric ranges without persisting signed URLs."""
    request = row.get("request") or {}
    response = row.get("response") or {}

    def header(headers, name, pattern):
        if not isinstance(headers, dict):
            return None
        value = next(
            (value for key, value in headers.items() if str(key).lower() == name),
            None,
        )
        return value if isinstance(value, str) and re.fullmatch(pattern, value) else None

    return {
        "method": request.get("type"),
        "host": urlsplit(request.get("url") or "").hostname,
        "start_time": str(request.get("start_time")),
        "duration_ms": request.get("duration_ms"),
        "range": header(request.get("headers"), "range", r"bytes=\d+-\d*"),
        "status": response.get("status"),
        "content_range": header(
            response.get("headers"), "content-range", r"bytes \d+-\d+/\d+"
        ),
    }


def collect_http_events(connection):
    rows = _frame_records(
        connection,
        "SELECT request, response FROM duckdb_logs_parsed('HTTP') ORDER BY timestamp",
    )
    return [sanitize_http_event(row) for row in rows] if isinstance(rows, list) else []


def sanitize_filesystem_event(row):
    """Preserve filesystem offsets while discarding signed remote paths."""
    def safe_name(value):
        return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", value) else None

    return {
        "timestamp": str(row.get("timestamp")),
        "fs": safe_name(row.get("fs")),
        "host": urlsplit(row.get("path") or "").hostname,
        "op": safe_name(row.get("op")),
        "bytes": row.get("bytes") if isinstance(row.get("bytes"), int) else None,
        "pos": row.get("pos") if isinstance(row.get("pos"), int) else None,
    }


def collect_filesystem_events(connection):
    rows = _frame_records(
        connection,
        "SELECT timestamp, fs, path, op, bytes, pos "
        "FROM duckdb_logs_parsed('FileSystem') ORDER BY timestamp",
    )
    return [sanitize_filesystem_event(row) for row in rows] if isinstance(rows, list) else []


@contextmanager
def trace_query_cursor(original_get_cursor, sink):
    """Read per-query diagnostics before the query cursor is closed."""
    with original_get_cursor() as cursor:
        try:
            yield cursor
        finally:
            started_ns = time.perf_counter_ns()
            try:
                profile = _frame_records(
                    cursor, "SELECT cache_httpfs_get_profile() AS profile"
                )
                http_events = collect_http_events(cursor)
                filesystem_events = collect_filesystem_events(cursor)
                sink.append({
                    "cache_profile": profile,
                    "http_events": http_events,
                    "filesystem_events": filesystem_events,
                    "capture_seconds": (time.perf_counter_ns() - started_ns) / 1e9,
                })
            except Exception as exc:
                sink.append({
                    "error": redact_secrets(str(exc)),
                    "capture_seconds": (time.perf_counter_ns() - started_ns) / 1e9,
                })


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
        connection_caching = payload.get("httpfs_connection_caching")
        if connection_caching is not None:
            ticker.duckdb_client.connection.execute(
                "SET GLOBAL httpfs_connection_caching = "
                + ("true" if connection_caching else "false")
            )
        cache_before = cache_snapshot(cache_directory)
        if diagnostics:
            cache_status_before = _frame_records(
                ticker.duckdb_client.connection,
                "SELECT * FROM cache_httpfs_cache_status_query()",
            )
            validate_cold_cache_status(cache_status_before)
        else:
            cache_status_before = []
        trace_io = diagnostics and bool(payload.get("trace_io"))
        cursor_diagnostics = []
        if trace_io:
            ticker.duckdb_client.connection.execute(
                "CALL enable_logging(['HTTP', 'FileSystem'], "
                "storage='memory', storage_buffer_size=0)"
            )
            original_get_cursor = ticker.duckdb_client._get_cursor
            ticker.duckdb_client._get_cursor = lambda: trace_query_cursor(
                original_get_cursor, cursor_diagnostics
            )

        query_event_offset = len(events)
        api_started_ns = time.perf_counter_ns()
        frame = ticker.price()
        api_ended_ns = time.perf_counter_ns()
        query_events = events[query_event_offset:]
        cache_profile = (
            _frame_records(
                ticker.duckdb_client.connection,
                "SELECT cache_httpfs_get_profile() AS profile",
            )
            if diagnostics else []
        )
        http_events = (
            collect_http_events(ticker.duckdb_client.connection) if trace_io else []
        )

    cache_after = cache_snapshot(cache_directory)
    if diagnostics:
        fingerprint = result_fingerprint(frame)
        if "symbol" not in frame or not frame["symbol"].eq(symbol).all():
            raise ValueError("Ticker.price returned data for an unexpected symbol")
        diagnostic_data = collect_diagnostics(
            ticker, cache_profile, http_events, cursor_diagnostics
        )
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
        if args.cache_block_size < 1:
            raise ValueError("cache block size must be positive")
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
        "cache_httpfs_cache_block_size": args.cache_block_size,
    }
    configured_settings = {
        **configuration,
        "http_proxy": redact_proxy(args.http_proxy),
    }
    if args.trace_io:
        configured_settings["trace_io"] = True
    if args.httpfs_connection_caching is not None:
        configured_settings["httpfs_connection_caching"] = args.httpfs_connection_caching
    methodology = {
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
    }
    if args.trace_io:
        methodology["secondary_metrics"] += ", and sanitized filesystem events"
        methodology["trace_effect"] = (
            "Filesystem logging and cursor diagnostics run inside the measured query"
        )
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
        "methodology": methodology,
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
                        "trace_io": args.trace_io,
                        "httpfs_connection_caching": args.httpfs_connection_caching,
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


def cmd_network_probe(args):
    try:
        if args.runs < 1 or not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("runs and timeout must be positive and finite")
        if args.block_size < 1:
            raise ValueError("block size must be positive")
        outcome = asyncio.run(run_network_probe(
            STOCK_PRICES_URL, args.http_proxy, args.runs, args.timeout, args.block_size
        ))
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as handle:
                json.dump(outcome, handle, indent=2, ensure_ascii=True)
                handle.write("\n")
    except Exception as exc:
        print(f"Error: {redact_secrets(str(exc))}", file=sys.stderr)
        return 1
    print(
        f"Network-only median: {outcome['median_wall_seconds']:.6f} s; "
        f"warmup: {outcome['warmup_seconds']:.6f} s; "
        f"HTTP: {outcome['warmup_http_version']}"
    )
    for sample in outcome["samples"]:
        print(
            f"[{sample['trial']}/{outcome['runs']}] "
            f"{sample['bytes']} bytes in {sample['wall_seconds']:.6f} s"
        )
    if args.output is not None:
        print(f"Record: {args.output}")
    return 0


def cmd_network_causality(args):
    try:
        if (not math.isfinite(args.timeout) or args.timeout <= 0
                or args.block_size < 1 or args.new_warmup_bytes < 1
                or not math.isfinite(args.idle_seconds) or args.idle_seconds < 0):
            raise ValueError("timeout, block size, warmup bytes, and idle seconds are invalid")
        outcome = asyncio.run(run_network_causality_probe(
            STOCK_PRICES_URL, args.http_proxy, args.timeout, args.block_size,
            args.new_warmup_bytes, args.idle_seconds,
        ))
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as handle:
                json.dump(outcome, handle, indent=2, ensure_ascii=True)
                handle.write("\n")
    except Exception as exc:
        print(f"Error: {redact_secrets(str(exc))}", file=sys.stderr)
        return 1
    for stage in outcome["stages"]:
        ports = sorted({
            item["local_port"] for item in stage["transfers"]
            if item["local_port"] is not None
        })
        print(
            f"{stage['label']}: {stage['bytes']} bytes in "
            f"{stage['wall_seconds']:.6f} s; local ports: {ports}"
        )
    if args.output is not None:
        print(f"Record: {args.output}")
    return 0


def cmd_network_transport(args):
    try:
        if (args.runs < 1 or not math.isfinite(args.timeout) or args.timeout <= 0
                or args.block_size < 1):
            raise ValueError("runs, timeout, and block size must be positive")
        outcome = asyncio.run(run_network_transport_probe(
            STOCK_PRICES_URL, args.http_proxy, args.runs, args.timeout, args.block_size
        ))
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as handle:
                json.dump(outcome, handle, indent=2, ensure_ascii=True)
                handle.write("\n")
    except Exception as exc:
        print(f"Error: {redact_secrets(str(exc))}", file=sys.stderr)
        return 1
    for sample in outcome["samples"]:
        print(
            f"[{sample['trial']}/{outcome['runs_per_mode']}] {sample['mode']}: "
            f"{sample['bytes']} bytes in {sample['wall_seconds']:.6f} s "
            f"({sample['effective_mbps']:.3f} Mbit/s)"
        )
    if args.output is not None:
        print(f"Record: {args.output}")
    return 0


def cmd_network_fanout(args):
    try:
        if (args.runs < 1 or not math.isfinite(args.timeout) or args.timeout <= 0
                or args.block_size < 1):
            raise ValueError("runs, timeout, and block size must be positive")
        outcome = asyncio.run(run_network_fanout_probe(
            STOCK_PRICES_URL, args.http_proxy, args.runs, args.timeout, args.block_size
        ))
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as handle:
                json.dump(outcome, handle, indent=2, ensure_ascii=True)
                handle.write("\n")
    except Exception as exc:
        print(f"Error: {redact_secrets(str(exc))}", file=sys.stderr)
        return 1
    for sample in outcome["samples"]:
        print(
            f"[{sample['trial']}/{outcome['runs_per_mode']}] "
            f"{sample['chunk_size']} B x {sample['connections']} connections "
            f"({sample['requests']} requests): {sample['bytes']} bytes in "
            f"{sample['wall_seconds']:.6f} s ({sample['effective_mbps']:.3f} Mbit/s)"
        )
    if args.output is not None:
        print(f"Record: {args.output}")
    return 0


def cmd_fsspec_probe(args):
    try:
        if args.runs < 1 or not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("runs and timeout must be positive and finite")
        if args.block_size < 1:
            raise ValueError("block size must be positive")
        outcome = run_fsspec_probe(args.http_proxy, args.runs, args.timeout, args.block_size)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as handle:
                json.dump(outcome, handle, indent=2, ensure_ascii=True)
                handle.write("\n")
    except Exception as exc:
        print(f"Error: {redact_secrets(str(exc))}", file=sys.stderr)
        return 1
    print(
        f"DuckDB/fsspec prototype median: {outcome['median_query_seconds']:.6f} s; "
        f"HTTP: {outcome['warmup_http_version']}"
    )
    for sample in outcome["samples"]:
        print(
            f"[{sample['trial']}/{len(outcome['samples'])}] "
            f"{sample['cached_bytes']} bytes in {sample['query_seconds']:.6f} s"
        )
    if args.output is not None:
        print(f"Record: {args.output}")
    return 0


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
    run_parser.add_argument("--cache-block-size", type=int, default=1024 * 1024)
    run_parser.add_argument("--trace-io", action="store_true")
    run_parser.add_argument(
        "--httpfs-connection-caching",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    run_parser.add_argument(
        "--keep-alive", action=argparse.BooleanOptionalAction, default=True
    )
    run_parser.add_argument(
        "--resolve-direct", action=argparse.BooleanOptionalAction, default=True
    )
    run_parser.add_argument("--output", type=Path, default=ROOT / "results")

    probe_parser = subparsers.add_parser(
        "network-probe", help="Measure three parallel Range GETs over a warmed HTTP pool"
    )
    probe_parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    probe_parser.add_argument("--http-proxy")
    probe_parser.add_argument("--timeout", type=float, default=60.0)
    probe_parser.add_argument("--block-size", type=int, default=1024 * 1024)
    probe_parser.add_argument("--output", type=Path)

    causality_parser = subparsers.add_parser(
        "network-causality",
        help="Cross connection reuse with repeated and fresh Range requests",
    )
    causality_parser.add_argument("--http-proxy")
    causality_parser.add_argument("--timeout", type=float, default=60.0)
    causality_parser.add_argument("--block-size", type=int, default=1024 * 1024)
    causality_parser.add_argument("--new-warmup-bytes", type=int, default=1)
    causality_parser.add_argument("--idle-seconds", type=float, default=0.0)
    causality_parser.add_argument("--output", type=Path)

    transport_parser = subparsers.add_parser(
        "network-transport",
        help="Compare multiplexed HTTP/2 with independent HTTP/2 and HTTP/1.1 connections",
    )
    transport_parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    transport_parser.add_argument("--http-proxy")
    transport_parser.add_argument("--timeout", type=float, default=60.0)
    transport_parser.add_argument("--block-size", type=int, default=1024 * 1024)
    transport_parser.add_argument("--output", type=Path)

    fanout_parser = subparsers.add_parser(
        "network-fanout",
        help="Compare HTTP/2 Range chunk sizes over 3, 6, and 12 warm connections",
    )
    fanout_parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    fanout_parser.add_argument("--http-proxy")
    fanout_parser.add_argument("--timeout", type=float, default=60.0)
    fanout_parser.add_argument("--block-size", type=int, default=1024 * 1024)
    fanout_parser.add_argument("--output", type=Path)

    fsspec_parser = subparsers.add_parser(
        "fsspec-probe", help="Measure experimental DuckDB reads over parallel HTTP/2 ranges"
    )
    fsspec_parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    fsspec_parser.add_argument("--http-proxy")
    fsspec_parser.add_argument("--timeout", type=float, default=60.0)
    fsspec_parser.add_argument("--block-size", type=int, default=1024 * 1024)
    fsspec_parser.add_argument("--output", type=Path)

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
    if args.command == "network-probe":
        return cmd_network_probe(args)
    if args.command == "network-causality":
        return cmd_network_causality(args)
    if args.command == "network-transport":
        return cmd_network_transport(args)
    if args.command == "network-fanout":
        return cmd_network_fanout(args)
    if args.command == "fsspec-probe":
        return cmd_fsspec_probe(args)
    if args.command == "archive":
        return cmd_archive(args)
    raise AssertionError(f"unknown command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
