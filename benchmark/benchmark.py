"""End-to-end DefeatBeta API benchmark and immutable result archive CLI."""

import argparse
import asyncio
from contextlib import AsyncExitStack, contextmanager
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import platform
import re
try:
    import resource
except ImportError:
    resource = None
import statistics
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
from urllib.parse import urlsplit
import uuid


def process_usage():
    """Expose comparable process counters on Unix and Windows."""
    if resource is not None:
        return resource.getrusage(resource.RUSAGE_SELF)
    import psutil
    from types import SimpleNamespace

    process = psutil.Process()
    cpu = process.cpu_times()
    memory = process.memory_info()
    return SimpleNamespace(
        ru_utime=cpu.user,
        ru_stime=cpu.system,
        ru_maxrss=getattr(memory, "peak_wset", memory.rss),
        ru_minflt=getattr(memory, "pfaults", 0),
        ru_majflt=getattr(memory, "pageins", 0),
    )


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
API_FILES = {
    "price": "stock_prices",
    "info": "stock_profile",
    "sec_filing": "stock_sec_filing",
    "officers": "stock_officers",
    "calendar": "stock_earning_calendar",
    "splits": "stock_split_events",
    "dividends": "stock_dividend_events",
    "ttm_eps": "stock_tailing_eps",
    "shares": "stock_shares_outstanding",
}

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
    "resolve_cdn_for_uncached_reads",
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
    client, url, name, start, end, total, sample_started_ns, include_body=False,
    trace_transport=False,
):
    request_started_ns = time.perf_counter_ns()
    first_body_ns = None
    length = 0
    digest = hashlib.sha256()
    body = bytearray() if include_body else None
    headers = {"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"}
    transport_events = []

    async def record_transport_event(event_name, info):
        event = {
            "name": event_name,
            "seconds": (time.perf_counter_ns() - sample_started_ns) / 1e9,
        }
        if isinstance(info.get("exception"), BaseException):
            event["error_type"] = type(info["exception"]).__name__
        transport_events.append(event)

    stream_options = (
        {"extensions": {"trace": record_transport_event}}
        if trace_transport else {}
    )
    async with client.stream("GET", url, headers=headers, **stream_options) as response:
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
    if trace_transport:
        result["transport_events"] = transport_events
    return result


ROWGROUP_PROBE_MODES = ("single", "split_2", "split_3")


def load_rowgroup_probe_metadata(footer_path):
    """Validate a cached footer extent without a persisted parsed index."""
    footer_path = Path(footer_path)
    match = re.search(r"-(\d+)-(\d+)\.footer$", footer_path.name)
    if match is None:
        raise ValueError("invalid footer filename")
    start, length = map(int, match.groups())
    size = start + length
    if size < 12 or length < 8 or length > 16 * 1024 * 1024:
        raise ValueError("invalid footer extent size")
    stored = footer_path.read_bytes()
    content = stored[32:]
    digest = hashlib.sha256(content).digest()
    if len(stored) != length + 32 or stored[:32] != digest:
        raise ValueError("footer digest does not match cached content")
    footer_size = int.from_bytes(content[-8:-4], "little")
    footer_start = size - footer_size - 8
    if (content[-4:] != b"PAR1" or footer_size <= 0
            or footer_start < max(4, start)):
        raise ValueError("invalid Parquet footer extent")
    return {
        "file_size": size, "extent_start": start,
        "footer_start": footer_start,
        "footer_sha256": digest.hex(),
        "footer_bytes": content[footer_start - start:],
    }


def parse_rowgroup_rows_from_footer(footer_bytes):
    """Let DuckDB parse the cached Parquet footer without downloading data."""
    try:
        import duckdb
        from defeatbeta_api.client.dataset_cache_fs import parquet_metadata_file
    except ImportError as exc:
        raise RuntimeError("install DuckDB to inspect cached Parquet metadata") from exc
    with parquet_metadata_file(footer_bytes) as synthetic:
        connection = duckdb.connect(":memory:")
        try:
            return connection.execute(
                "SELECT row_group_id, path_in_schema, stats_min_value, "
                "stats_max_value, "
                "COALESCE(dictionary_page_offset, data_page_offset), "
                "total_compressed_size FROM parquet_metadata(?)",
                [synthetic],
            ).fetchall()
        finally:
            connection.close()


def rowgroup_probe_plan(rows, footer_start, count, group_offset=0):
    """Select disjoint, similarly sized complete row-group byte spans."""
    if count < 1 or footer_start < 12 or group_offset < 0:
        raise ValueError("invalid row-group probe bounds")
    groups = {}
    for row in rows:
        if (not isinstance(row, (list, tuple)) or len(row) != 6
                or type(row[0]) is not int or row[0] < 0
                or not isinstance(row[1], str)
                or type(row[4]) is not int or type(row[5]) is not int
                or row[4] < 4 or row[5] <= 0
                or row[4] + row[5] > footer_start):
            raise ValueError("invalid row-group column chunk")
        groups.setdefault(row[0], []).append(row)
    candidates = []
    for group_id, chunks in groups.items():
        if not any(chunk[1] == "symbol" for chunk in chunks):
            continue
        start = min(chunk[4] for chunk in chunks)
        end = max(chunk[4] + chunk[5] for chunk in chunks) - 1
        candidates.append({
            "row_group_id": group_id, "start": start, "end": end,
            "bytes": end - start + 1,
        })
    candidates.sort(key=lambda item: item["start"])
    if any(left["end"] >= right["start"]
           for left, right in zip(candidates, candidates[1:])):
        raise ValueError("row-group byte spans overlap")
    if not candidates:
        raise ValueError("not enough comparable row groups")
    median_size = statistics.median(item["bytes"] for item in candidates)
    comparable = [item for item in candidates
                  if 0.9 * median_size <= item["bytes"] <= 1.1 * median_size]
    if len(comparable) < count:
        raise ValueError("not enough comparable row groups")
    selected = []
    for slot in range(count):
        first = (slot * len(comparable)) // count
        last = ((slot + 1) * len(comparable)) // count
        if first + group_offset >= last:
            raise ValueError("group offset exceeds the available row-group spacing")
        selected.append(comparable[first + group_offset])
    return selected


def rowgroup_probe_schedule(runs, mode_offset=0):
    if runs < 1 or mode_offset not in (0, 1, 2):
        raise ValueError("runs or mode offset is invalid")
    return [(trial + 1, mode)
            for trial in range(runs)
            for mode in (ROWGROUP_PROBE_MODES[(trial + mode_offset) % 3:]
                         + ROWGROUP_PROBE_MODES[:(trial + mode_offset) % 3])]


def split_probe_range(start, end, parts):
    length = end - start + 1
    if start < 0 or length < parts or parts < 1:
        raise ValueError("invalid split Range bounds")
    width, remainder = divmod(length, parts)
    boundaries = [start + part * width + min(part, remainder)
                  for part in range(parts + 1)]
    return [(boundaries[part], boundaries[part + 1] - 1)
            for part in range(parts)]


def probe_transfer_phases(transfer):
    """Report distinct intervals instead of sample-relative timestamps."""
    first_body = transfer["first_body_seconds"]
    if first_body is None:
        raise ValueError("Range response had no body")
    return {
        "headers_wait_seconds": (
            transfer["headers_seconds"] - transfer["request_start_seconds"]
        ),
        "first_body_wait_seconds": first_body - transfer["headers_seconds"],
        "body_transfer_seconds": transfer["finish_seconds"] - first_body,
    }


async def run_rowgroup_network_probe(
    url, proxy, runs, timeout, footer_path,
    mode_offset=0, group_offset=0,
):
    """Compare complete cold row-group transfers on one verified file version."""
    try:
        import httpx
        import h2  # noqa: F401 - required by httpx HTTP/2 support
    except ImportError as exc:
        raise RuntimeError("install the optional httpx[http2] benchmark dependency") from exc

    metadata = load_rowgroup_probe_metadata(footer_path)
    schedule = rowgroup_probe_schedule(runs, mode_offset)
    plan = rowgroup_probe_plan(
        parse_rowgroup_rows_from_footer(metadata["footer_bytes"]),
        metadata["footer_start"], len(schedule), group_offset,
    )
    limits = httpx.Limits(max_connections=3, max_keepalive_connections=3,
                          keepalive_expiry=120)
    async with httpx.AsyncClient(
        http2=True, timeout=timeout, limits=limits, **httpx_proxy_options(proxy)
    ) as client:
        signed_url = await resolve_signed_url(client, url)
        verify_started_ns = time.perf_counter_ns()
        footer = await _probe_range(
            client, signed_url, "version_check", metadata["extent_start"],
            metadata["file_size"] - 1, metadata["file_size"], verify_started_ns,
        )
        if footer["sha256"] != metadata["footer_sha256"]:
            raise ValueError("remote footer digest differs from the local cache")
        samples = []
        for (trial, mode), group in zip(schedule, plan):
            parts = 1 if mode == "single" else int(mode[-1])
            ranges = split_probe_range(group["start"], group["end"], parts)
            started_ns = time.perf_counter_ns()
            transfers = await asyncio.gather(*(
                _probe_range(
                    client, signed_url, f"part_{index}", start, end,
                    metadata["file_size"], started_ns,
                )
                for index, (start, end) in enumerate(ranges)
            ))
            wall_seconds = (time.perf_counter_ns() - started_ns) / 1e9
            downloaded = sum(item["bytes"] for item in transfers)
            if downloaded != group["bytes"]:
                raise ValueError("split Range bytes do not match the row group")
            for transfer in transfers:
                transfer.update(probe_transfer_phases(transfer))
            samples.append({
                "trial": trial, "mode": mode, "row_group_id": group["row_group_id"],
                "start": group["start"], "end": group["end"],
                "bytes": downloaded, "wall_seconds": wall_seconds,
                "effective_mbps": downloaded * 8 / wall_seconds / 1e6,
                "transfers": transfers,
            })
    return {
        "probe": "verified_row_group_range_crossover",
        "url": url, "cdn_host": urlsplit(signed_url).hostname,
        "proxy": redact_proxy(proxy), "file_size": metadata["file_size"],
        "footer_sha256": metadata["footer_sha256"],
        "version_check_seconds": footer["finish_seconds"],
        "runs_per_mode": runs, "mode_offset": mode_offset,
        "group_offset": group_offset, "samples": samples,
        "limitations": (
            "Network-only diagnostic over disjoint, similarly sized row groups. "
            "It excludes DuckDB and the local cache. Proxy and CDN caches may "
            "operate at an unknown granularity; row groups are not byte-identical."
        ),
    }


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
            "Network-only diagnostic; it excludes DuckDB, the dataset cache, Parquet decoding, "
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
            "It excludes DuckDB, the dataset cache, Parquet decoding, and DataFrame materialization. "
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


def cold_read_modes(block_size):
    """Compare connection startup and chunking without changing query bytes."""
    if block_size < 4:
        raise ValueError("block size must be at least four bytes")
    return [
        (warmup, connections, chunk)
        for warmup in (0, block_size // 16, block_size // 4, block_size)
        for connections in (3, 6)
        for chunk in (block_size // 2, block_size // 4)
    ]


def cold_read_payload_hash(plan, transfers):
    """Verify that a split download reassembles the same ordered payload."""
    if len(plan) != len(transfers):
        raise ValueError("transfer length differs from the Range plan")
    digest = hashlib.sha256()
    for (_, start, end), item in zip(plan, transfers):
        body = item["body"]
        if len(body) != end - start + 1:
            raise ValueError("transfer length differs from the requested Range")
        digest.update(body)
    return digest.hexdigest()


def connection_crossover_plan(file_size, block_size, sample_index,
                              warmup_bytes, chunk_size,
                              include_heartbeat=False):
    """Reserve fresh, disjoint warmup and query ranges for one sample."""
    if (sample_index < 0 or warmup_bytes < 1 or warmup_bytes > block_size
            or chunk_size < 1):
        raise ValueError("invalid crossover range size or sample index")
    warm_base = (24 + sample_index * 8) * block_size
    warmup = [
        (f"warm_{index}", warm_base + index * block_size,
         warm_base + index * block_size + warmup_bytes - 1)
        for index in range(6)
    ]
    if warmup[-1][2] >= file_size:
        raise ValueError("file is too small for crossover warmup ranges")
    reference = network_range_plan(file_size, block_size)
    if len(reference) != 3:
        raise ValueError("file is too small for three query-equivalent ranges")
    query_blocks = causal_control_plan(
        file_size, block_size, 300 + sample_index * 4, reference
    )
    query = [
        (f"{name}_part_{part}", offset, min(offset + chunk_size - 1, end))
        for name, start, end in query_blocks
        for part, offset in enumerate(range(start, end + 1, chunk_size))
    ]
    if len(query) != 6:
        raise ValueError("crossover requires six query ranges")
    heartbeat = []
    if include_heartbeat:
        if block_size < 6:
            raise ValueError("heartbeat requires a block size of at least six")
        heartbeat = [
            (f"heartbeat_{index}", warm_base + 6 * block_size + index,
             warm_base + 6 * block_size + index)
            for index in range(6)
        ]
        if heartbeat[-1][2] >= file_size:
            raise ValueError("file is too small for heartbeat ranges")
    return {"warmup": warmup, "heartbeat": heartbeat, "query": query}


def validate_crossover_connections(mode, warm_ports, query_ports):
    if (len(query_ports) != 6 or None in query_ports
            or len(set(query_ports)) != 6):
        raise ValueError("query did not use six independent sockets")
    if mode == "none":
        if warm_ports:
            raise ValueError("unwarmed sample unexpectedly used warm sockets")
        return
    if (len(warm_ports) != 6 or None in warm_ports
            or len(set(warm_ports)) != 6):
        raise ValueError("warmup did not use six independent sockets")
    if mode == "same" and warm_ports != query_ports:
        raise ValueError("query did not reuse the same warm sockets")
    if mode == "other" and set(warm_ports) & set(query_ports):
        raise ValueError("query reused a warm socket")
    if mode not in ("same", "other"):
        raise ValueError("unknown crossover mode")


def crossover_connection_state(mode, warm_ports, query_ports):
    if mode == "same":
        if (len(warm_ports) != 6 or len(query_ports) != 6
                or None in warm_ports or None in query_ports
                or len(set(warm_ports)) != 6 or len(set(query_ports)) != 6):
            raise ValueError("same mode has unverifiable sockets")
        return "reused" if warm_ports == query_ports else "replaced"
    validate_crossover_connections(mode, warm_ports, query_ports)
    return "independent"


async def run_network_crossover_probe(url, proxy, runs, timeout, block_size,
                                      warmup_bytes, chunk_size, idle_seconds=0.0,
                                      sample_offset=0, modes=("same", "other", "none"),
                                      heartbeat_at_seconds=None):
    """Separate connection-state benefits from shared proxy/CDN cache effects."""
    try:
        import httpx
        import h2  # noqa: F401 - required by httpx HTTP/2 support
    except ImportError as exc:
        raise RuntimeError("install the optional httpx[http2] benchmark dependency") from exc
    if heartbeat_at_seconds is not None and (
        not math.isfinite(heartbeat_at_seconds)
        or not 0 < heartbeat_at_seconds < idle_seconds
        or tuple(modes) != ("same",)
    ):
        raise ValueError("heartbeat requires same mode and a time within idle period")

    limits = httpx.Limits(max_connections=1, max_keepalive_connections=1,
                          keepalive_expiry=120)

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
    samples = []
    for sequence, (trial, mode) in enumerate(fanout_probe_schedule(runs, modes)):
        sample_index = sample_offset + sequence
        plan = connection_crossover_plan(
            file_size, block_size, sample_index, warmup_bytes, chunk_size,
            include_heartbeat=heartbeat_at_seconds is not None,
        )
        async with AsyncExitStack() as stack:
            warm_clients = ([await stack.enter_async_context(new_client())
                             for _ in range(6)] if mode != "none" else [])
            warmup_seconds = 0.0
            warm_transfers = []
            warm_started_ns = time.perf_counter_ns()
            if warm_clients:
                warm_transfers = await asyncio.gather(*(
                    _probe_range(client, signed_url, name, start, end,
                                 file_size, warm_started_ns,
                                 trace_transport=True)
                    for client, (name, start, end) in zip(warm_clients, plan["warmup"])
                ))
                warmup_seconds = (time.perf_counter_ns() - warm_started_ns) / 1e9
            warm_finished_ns = time.perf_counter_ns()
            heartbeat_transfers = []
            heartbeat_seconds = 0.0
            if heartbeat_at_seconds is not None:
                await asyncio.sleep(heartbeat_at_seconds)
                heartbeat_started_ns = time.perf_counter_ns()
                heartbeat_transfers = await asyncio.gather(*(
                    _probe_range(client, signed_url, name, start, end,
                                 file_size, heartbeat_started_ns,
                                 trace_transport=True)
                    for client, (name, start, end) in zip(
                        warm_clients, plan["heartbeat"]
                    )
                ))
                heartbeat_seconds = (
                    time.perf_counter_ns() - heartbeat_started_ns
                ) / 1e9
                await asyncio.sleep(idle_seconds - heartbeat_at_seconds)
            elif idle_seconds:
                await asyncio.sleep(idle_seconds)
            query_clients = (warm_clients if mode == "same" else [
                await stack.enter_async_context(new_client()) for _ in range(6)
            ])
            query_started_ns = time.perf_counter_ns()
            query_transfers = await asyncio.gather(*(
                _probe_range(client, signed_url, name, start, end,
                             file_size, query_started_ns, include_body=True,
                             trace_transport=True)
                for client, (name, start, end) in zip(query_clients, plan["query"])
            ))
            query_seconds = (time.perf_counter_ns() - query_started_ns) / 1e9
            if any(item["http_version"] != "HTTP/2"
                   for item in warm_transfers + heartbeat_transfers + query_transfers):
                raise ValueError("crossover did not use HTTP/2")
            warm_ports = [item["local_port"] for item in warm_transfers]
            heartbeat_ports = [item["local_port"] for item in heartbeat_transfers]
            query_ports = [item["local_port"] for item in query_transfers]
            connection_state = crossover_connection_state(
                mode, warm_ports, query_ports
            )
            heartbeat_connection_state = (
                crossover_connection_state("same", warm_ports, heartbeat_ports)
                if heartbeat_transfers else None
            )
            post_heartbeat_connection_state = (
                crossover_connection_state("same", heartbeat_ports, query_ports)
                if heartbeat_transfers else None
            )
            digest = cold_read_payload_hash(plan["query"], query_transfers)
            for item in query_transfers:
                item.pop("body")
            samples.append({
                "trial": trial,
                "mode": mode,
                "warmup_seconds": warmup_seconds,
                "idle_seconds": idle_seconds,
                "actual_idle_seconds": (
                    query_started_ns - warm_finished_ns
                ) / 1e9,
                "connection_age_seconds": (
                    query_started_ns - warm_started_ns
                ) / 1e9,
                "warmup_bytes": sum(item["bytes"] for item in warm_transfers),
                "heartbeat_seconds": heartbeat_seconds,
                "heartbeat_bytes": sum(item["bytes"] for item in heartbeat_transfers),
                "query_seconds": query_seconds,
                "query_bytes": sum(item["bytes"] for item in query_transfers),
                "query_sha256": digest,
                "warm_ports": warm_ports,
                "heartbeat_ports": heartbeat_ports,
                "query_ports": query_ports,
                "connection_state": connection_state,
                "heartbeat_connection_state": heartbeat_connection_state,
                "post_heartbeat_connection_state": post_heartbeat_connection_state,
                "warmup_ranges": plan["warmup"] if warm_clients else [],
                "heartbeat_ranges": plan["heartbeat"],
                "query_ranges": plan["query"],
                "warmup_transfers": warm_transfers,
                "heartbeat_transfers": heartbeat_transfers,
                "query_transfers": query_transfers,
            })
    return {
        "probe": "connection_state_vs_shared_remote_cache",
        "url": url,
        "cdn_host": urlsplit(signed_url).hostname,
        "proxy": redact_proxy(proxy),
        "file_size": file_size,
        "block_size": block_size,
        "warmup_bytes_per_connection": warmup_bytes,
        "chunk_size": chunk_size,
        "idle_seconds": idle_seconds,
        "heartbeat_at_seconds": heartbeat_at_seconds,
        "sample_offset": sample_offset,
        "runs_per_mode": runs,
        "median_query_seconds_by_mode": {
            mode: statistics.median(
                sample["query_seconds"] for sample in samples if sample["mode"] == mode
            )
            for mode in modes
        },
        "samples": samples,
        "limitations": (
            "Each sample uses fresh, disjoint file ranges with identical transfer lengths. "
            "The other mode warms separate sockets while keeping them open during query. "
            "Local ports identify application-to-proxy sockets, not necessarily proxy "
            "upstream sockets. Proxy/CDN cache granularity and competing traffic remain "
            "uncontrolled. This probe does not directly measure remote sender cwnd."
        ),
    }


async def run_network_cold_read_probe(url, proxy, runs, timeout, block_size):
    """Compare fresh and warmed independent connections for query-equivalent bytes."""
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
    modes = cold_read_modes(block_size)
    if len(network_range_plan(file_size, block_size)) != 3:
        raise ValueError("file is too small for the three query-equivalent ranges")
    schedule = fanout_probe_schedule(runs, modes)
    expected_hash = None
    samples = []
    for trial, (warmup_bytes, connections, chunk_size) in schedule:
        plan = network_fanout_plan(file_size, block_size, chunk_size)
        if connections > len(plan):
            raise ValueError("connection count exceeds the number of query ranges")
        # Each trial and connection warms a distinct, non-query range.
        neutral_start = (24 + (trial - 1) * 8) * block_size
        if neutral_start + connections * block_size > file_size:
            raise ValueError("file is too small for disjoint warmup ranges")
        async with AsyncExitStack() as stack:
            clients = [await stack.enter_async_context(new_client())
                       for _ in range(connections)]
            warmup_seconds = 0.0
            warmup_ports = None
            if warmup_bytes:
                warm_started_ns = time.perf_counter_ns()
                warm_results = await asyncio.gather(*(
                    _probe_range(
                        client, signed_url, f"warm_{index}",
                        neutral_start + index * block_size,
                        neutral_start + index * block_size + warmup_bytes - 1,
                        file_size, warm_started_ns,
                    )
                    for index, client in enumerate(clients)
                ))
                warmup_seconds = (time.perf_counter_ns() - warm_started_ns) / 1e9
                warmup_ports = [item["local_port"] for item in warm_results]
                if (any(item["http_version"] != "HTTP/2" for item in warm_results)
                        or None in warmup_ports
                        or len(set(warmup_ports)) != connections):
                    raise ValueError("warmup did not create independent HTTP/2 connections")
            assigned_indices = [index % connections for index in range(len(plan))]
            started_ns = time.perf_counter_ns()
            transfers = await asyncio.gather(*(
                _probe_range(
                    clients[assigned_indices[index]], signed_url, name, start, end,
                    file_size, started_ns, include_body=True,
                )
                for index, (name, start, end) in enumerate(plan)
            ))
            query_seconds = (time.perf_counter_ns() - started_ns) / 1e9
            if warmup_ports is not None:
                validate_fanout_connections(transfers, warmup_ports, assigned_indices)
            else:
                ports_by_client = {}
                for item, index in zip(transfers, assigned_indices):
                    port = item["local_port"]
                    if item["http_version"] != "HTTP/2" or port is None:
                        raise ValueError("cold sample did not use verifiable HTTP/2 connections")
                    if index in ports_by_client and ports_by_client[index] != port:
                        raise ValueError("cold sample replaced a connection")
                    ports_by_client[index] = port
                if len(set(ports_by_client.values())) != connections:
                    raise ValueError("cold sample did not use independent connections")
            payload_hash = cold_read_payload_hash(plan, transfers)
            if expected_hash is not None and payload_hash != expected_hash:
                raise ValueError("Range content changed between cold-read modes")
            expected_hash = payload_hash
            for item in transfers:
                item.pop("body")
            total_bytes = sum(item["bytes"] for item in transfers)
            samples.append({
                "trial": trial,
                "warmup_bytes_per_connection": warmup_bytes,
                "warmup_seconds": warmup_seconds,
                "connections": connections,
                "chunk_size": chunk_size,
                "query_seconds": query_seconds,
                "query_bytes": total_bytes,
                "query_mbps": total_bytes * 8 / query_seconds / 1e6,
                "payload_sha256": payload_hash,
                "transfers": transfers,
            })
    return {
        "probe": "query_equivalent_fresh_connection_comparison",
        "url": url,
        "cdn_host": urlsplit(signed_url).hostname,
        "proxy": redact_proxy(proxy),
        "file_size": file_size,
        "block_size": block_size,
        "runs_per_mode": runs,
        "samples": samples,
        "limitations": (
            "Network-only diagnostic. Timed bytes match the three price-query blocks, "
            "but this excludes the API, DuckDB, cache, Parquet decoding, and DataFrame. "
            "Connections are new for every sample. Warmup is outside query timing and "
            "its time and bytes are reported separately. Query ranges repeat across modes; "
            "proxy and CDN caches cannot be excluded."
        ),
    }


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
            "It excludes DuckDB, the dataset cache, Parquet decoding, and DataFrame materialization. "
            "Shared proxy traffic and remote caches are uncontrolled."
        ),
    }


def cache_snapshot(directory):
    root = Path(directory)
    control_files = {".dataset-cache.lock", ".dataset-version.json"}
    files = [
        path for path in root.rglob("*")
        if path.is_file() and path.name not in control_files
    ]
    return {
        "files": len(files),
        "bytes": sum(path.stat().st_size for path in files),
    }


def data_cache_snapshot(directory):
    """Count demand-fetched data extents, excluding metadata and the Parquet magic."""
    files = [
        path for path in Path(directory).rglob("*.block")
        if not path.is_symlink() and not path.name.endswith(".parquet-0-4.block")
    ]
    return {"files": len(files), "bytes": sum(path.stat().st_size for path in files)}


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


def _merge_intervals(intervals):
    merged = []
    for start, end in sorted(intervals):
        if start >= end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _intersect_intervals(left, right):
    intersection = []
    left = _merge_intervals(left)
    right = _merge_intervals(right)
    i = j = 0
    while i < len(left) and j < len(right):
        start = max(left[i][0], right[j][0])
        end = min(left[i][1], right[j][1])
        if start < end:
            intersection.append((start, end))
        if left[i][1] <= right[j][1]:
            i += 1
        else:
            j += 1
    return intersection


def classify_parquet_io(events, chunks, file_size, footer_size):
    """Attribute half-open file reads to Parquet chunks, footer, and gaps."""
    if (not isinstance(file_size, int) or not isinstance(footer_size, int)
            or file_size < 12 or footer_size <= 0
            or footer_size + 12 > file_size):
        raise ValueError("Invalid Parquet file or footer size")
    footer_start = file_size - footer_size - 8
    regions = [(0, 4, "header", None, None)]
    for row_group_id, column, start, size in chunks:
        if (not isinstance(row_group_id, int) or not isinstance(column, str)
                or not isinstance(start, int) or not isinstance(size, int)
                or start < 4 or size <= 0 or start + size > footer_start):
            raise ValueError("Invalid Parquet column chunk")
        regions.append((start, start + size, "column_chunk", row_group_id, column))
    regions.append((footer_start, file_size, "footer", None, None))
    regions.sort(key=lambda item: item[0])
    if any(left[1] > right[0] for left, right in zip(regions, regions[1:])):
        raise ValueError("Parquet physical regions overlap")

    def segment(kind, group, column, start, end):
        return {
            "kind": kind, "row_group_id": group, "column": column,
            "start": start, "end": end, "bytes": end - start,
        }

    classified = []
    for event in events:
        start, end = event.get("start"), event.get("end")
        if (not isinstance(start, int) or not isinstance(end, int)
                or start < 0 or start >= end or end > file_size):
            raise ValueError("I/O range is outside the file")
        cursor = start
        pieces = []
        for region_start, region_end, kind, group, column in regions:
            if region_end <= cursor:
                continue
            if region_start >= end:
                break
            if cursor < region_start:
                gap_end = min(region_start, end)
                pieces.append(segment("unmapped", None, None, cursor, gap_end))
                cursor = gap_end
            overlap_end = min(region_end, end)
            if cursor < overlap_end:
                pieces.append(segment(kind, group, column, cursor, overlap_end))
                cursor = overlap_end
            if cursor >= end:
                break
        if cursor < end:
            pieces.append(segment("unmapped", None, None, cursor, end))
        classified.append({
            "sequence": event.get("sequence"), "start": start, "end": end,
            "segments": pieces,
        })
    return classified


def sample_parquet_io_events(sample, file_name):
    """Extract complete query-time reads and inclusive HTTP transfers for one file."""
    reads = []
    ranges = []
    after = []
    object_ids = set()

    def append_matching(source, target, inclusive):
        for event in source:
            if event.get("file") != file_name:
                continue
            if event.get("object_id"):
                object_ids.add(event["object_id"])
            end = event.get("end")
            target.append({
                "sequence": event.get("sequence"),
                "start": event.get("start"),
                "end": end + 1 if inclusive and isinstance(end, int) else end,
            })

    for event in sample.get("performance_events", []):
        if event.get("name") != "duckdb.dataset_cache.io":
            continue
        if (event.get("reads_complete") is False
                or event.get("ranges_complete") is False):
            raise ValueError("Parquet I/O event capture is incomplete")
        append_matching(event.get("reads", []), reads, False)
        append_matching(event.get("ranges", []), ranges, True)
    if sample.get("range_events_after_prefetch_drain_complete") is False:
        raise ValueError("Parquet I/O event capture is incomplete")
    append_matching(sample.get("range_events_after_prefetch_drain", []), after, True)
    if len(object_ids) > 1:
        raise ValueError("Parquet I/O events include multiple objects with one file name")
    return reads, ranges, after


def _compact_read(stream, length, limit):
    if length < 0 or stream.tell() + length > limit:
        raise ValueError("Truncated Parquet page header at column chunk boundary")
    content = stream.read(length)
    if len(content) != length:
        raise ValueError("Truncated Parquet page header")
    return content


def _compact_varint(stream, limit):
    value = 0
    for shift in range(0, 70, 7):
        byte = _compact_read(stream, 1, limit)
        value |= (byte[0] & 0x7f) << shift
        if not byte[0] & 0x80:
            return value
    raise ValueError("Invalid Parquet page header varint")


def _compact_skip(stream, wire_type, limit):
    if wire_type in (1, 2):
        return
    if wire_type == 3:
        length = 1
    elif wire_type in (4, 5, 6):
        _compact_varint(stream, limit)
        return
    elif wire_type == 7:
        length = 8
    elif wire_type == 8:
        length = _compact_varint(stream, limit)
    elif wire_type in (9, 10):
        header = _compact_read(stream, 1, limit)
        count = header[0] >> 4
        if count == 15:
            count = _compact_varint(stream, limit)
        for _ in range(count):
            _compact_skip(stream, header[0] & 15, limit)
        return
    elif wire_type == 11:
        count = _compact_varint(stream, limit)
        if count:
            types = _compact_read(stream, 1, limit)
            for _ in range(count):
                _compact_skip(stream, types[0] >> 4, limit)
                _compact_skip(stream, types[0] & 15, limit)
        return
    elif wire_type == 12:
        _compact_struct(stream, (), limit)
        return
    else:
        raise ValueError("Unsupported Parquet page header type")
    _compact_read(stream, length, limit)


def _compact_struct(stream, wanted, limit):
    result = {}
    previous = 0
    while True:
        header = _compact_read(stream, 1, limit)
        if header[0] == 0:
            return result
        field_id = previous + (header[0] >> 4)
        if header[0] >> 4 == 0:
            raw = _compact_varint(stream, limit)
            field_id = (raw >> 1) ^ -(raw & 1)
        previous = field_id
        wire_type = header[0] & 15
        if field_id in wanted and wire_type in (4, 5, 6):
            raw = _compact_varint(stream, limit)
            result[field_id] = (raw >> 1) ^ -(raw & 1)
        elif field_id in (5, 7, 8) and 1 in wanted and wire_type == 12:
            nested = _compact_struct(stream, (1,), limit)
            result[field_id] = nested.get(1)
        else:
            _compact_skip(stream, wire_type, limit)


def inspect_parquet_pages(parquet, chunks):
    """Read physical page headers for selected footer-described column chunks."""
    pages = []
    page_types = {0: "data", 1: "index", 2: "dictionary", 3: "data_v2"}
    with Path(parquet).open("rb") as stream:
        for row_group_id, column, start, size in sorted(chunks, key=lambda row: row[2]):
            chunk_end = start + size
            stream.seek(start)
            while stream.tell() < chunk_end:
                page_start = stream.tell()
                fields = _compact_struct(stream, (1, 2, 3), chunk_end)
                if not all(field in fields for field in (1, 2, 3)):
                    raise ValueError("Parquet page header is missing required fields")
                payload_start = stream.tell()
                compressed_size = fields[3]
                page_end = payload_start + compressed_size
                if (payload_start <= page_start or payload_start - page_start > 1024 * 1024
                        or compressed_size < 0 or page_end > chunk_end):
                    raise ValueError("Parquet page exceeds its column chunk")
                pages.append({
                    "row_group_id": row_group_id,
                    "column": column,
                    "type": page_types.get(fields[1], f"unknown_{fields[1]}"),
                    "start": page_start,
                    "end": page_end,
                    "header_bytes": payload_start - page_start,
                    "compressed_bytes": compressed_size,
                    "uncompressed_bytes": fields[2],
                    "num_values": fields.get(8 if fields[1] == 3 else
                                             7 if fields[1] == 2 else 5),
                })
                stream.seek(page_end)
            if stream.tell() != chunk_end:
                raise ValueError("Parquet pages do not cover their column chunk")
    return pages


def prefetch_coverage(events, extra_ranges=(), extra_ranges_complete=True):
    """Compare prefetched network bytes with DuckDB's requested byte ranges."""
    if not extra_ranges_complete or any(
        event.get("name") == "duckdb.dataset_cache.io"
        and (event.get("ranges_complete") is False
             or event.get("reads_complete") is False)
        for event in events
    ):
        return {
            "complete": False,
            "planned_downloaded_bytes": None,
            "planned_read_bytes": None,
            "planned_unread_bytes": None,
        }

    def identity(item):
        object_id = item.get("object_id")
        return ("object", object_id) if object_id else ("file", item.get("file"))

    planned = {}
    downloaded = {}
    read = {}
    for event in events:
        if event.get("name") == "duckdb.prefetch_ranges":
            planned.setdefault(identity(event), []).extend(
                tuple(interval) for interval in event.get("planned_intervals", [])
            )
        elif event.get("name") == "duckdb.dataset_cache.io":
            for transfer in event.get("ranges", []):
                downloaded.setdefault(identity(transfer), []).append(
                    (transfer["start"], transfer["end"] + 1)
                )
            for request in event.get("reads", []):
                read.setdefault(identity(request), []).append(
                    (request["start"], request["end"])
                )
    for transfer in extra_ranges:
        downloaded.setdefault(identity(transfer), []).append(
            (transfer["start"], transfer["end"] + 1)
        )
    planned_downloaded = 0
    planned_read = 0
    for file, intervals in planned.items():
        transferred = _intersect_intervals(intervals, downloaded.get(file, []))
        planned_downloaded += sum(end - start for start, end in transferred)
        planned_read += sum(
            end - start for start, end in
            _intersect_intervals(transferred, read.get(file, []))
        )
    return {
        "complete": True,
        "planned_downloaded_bytes": planned_downloaded,
        "planned_read_bytes": planned_read,
        "planned_unread_bytes": planned_downloaded - planned_read,
    }


def _frame_records(connection, sql):
    try:
        frame = connection.execute(sql).df()
        return redact_secrets(frame.to_dict(orient="records"))
    except Exception as exc:
        return {"error": redact_secrets(str(exc))}


def collect_diagnostics(ticker, http_events=None, cursor_diagnostics=None):
    connection = ticker.duckdb_client.connection
    settings = _frame_records(
        connection,
        "SELECT name, value FROM duckdb_settings() "
        "WHERE name LIKE 'http_%' "
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
        "cache_metrics": ticker.duckdb_client._dataset_fs.metrics()
        if getattr(ticker.duckdb_client, "_dataset_fs", None) is not None else None,
        "cache_warmup_metrics": ticker.duckdb_client._dataset_fs.warmup_metrics()
        if getattr(ticker.duckdb_client._dataset_fs, "warmup_metrics", None) else None,
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
                http_events = collect_http_events(cursor)
                filesystem_events = collect_filesystem_events(cursor)
                sink.append({
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
    """Run one real Ticker API call against an isolated local cache."""
    symbol = validate_symbol(payload["symbol"])
    api_method = payload.get("api_method", "price")
    if api_method not in API_FILES:
        raise ValueError("Unsupported Ticker API method")
    cache_directory = Path(payload["cache_directory"])
    if not cache_directory.is_dir() or any(cache_directory.iterdir()):
        raise ValueError("worker requires an existing, empty, isolated cache directory")

    import_started_ns = time.perf_counter_ns()
    api = api or load_api_bindings()
    imported_ns = time.perf_counter_ns()
    events = []
    configuration_values = dict(payload.get("configuration", {}))
    configuration_values["cache_directory"] = str(cache_directory)
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
        connection_warmup_seconds = 0.0
        warmup_bytes = payload.get("cache_connection_warmup_bytes", 0)
        if warmup_bytes:
            if api_method != "price":
                raise ValueError("Connection warmup is available only for price")
            warm_started_ns = time.perf_counter_ns()
            ticker.duckdb_client._dataset_fs.prepare_connections(
                STOCK_PRICES_URL, warmup_bytes
            )
            connection_warmup_seconds = (
                time.perf_counter_ns() - warm_started_ns
            ) / 1e9
        cache_before = cache_snapshot(cache_directory)
        data_cache_before = data_cache_snapshot(cache_directory)
        if cache_before["files"] or data_cache_before["files"]:
            raise ValueError("dataset cache was not empty before the API call")
        dataset_fs = getattr(getattr(ticker, "duckdb_client", None), "_dataset_fs", None)
        metrics_before_query = (
            dataset_fs.metrics() if dataset_fs is not None
            and hasattr(dataset_fs, "metrics") else None
        )
        warmup_metrics_before_query = (
            dataset_fs.warmup_metrics() if dataset_fs is not None
            and hasattr(dataset_fs, "warmup_metrics") else None
        )
        range_event_offset = (
            dataset_fs.range_event_sequence()
            if dataset_fs is not None and hasattr(dataset_fs, "range_event_sequence")
            else None
        )
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
        frame = getattr(ticker, api_method)()
        api_ended_ns = time.perf_counter_ns()
        metrics_after_query = (
            dataset_fs.metrics() if metrics_before_query is not None else None
        )
        drain_started_ns = time.perf_counter_ns()
        prefetch_drain = (
            dataset_fs.await_pending()
            if dataset_fs is not None and hasattr(dataset_fs, "await_pending")
            else {"futures": 0, "errors": 0}
        )
        prefetch_drain_seconds = (time.perf_counter_ns() - drain_started_ns) / 1e9
        metrics_after_prefetch = (
            dataset_fs.metrics() if metrics_before_query is not None else None
        )
        if range_event_offset is not None:
            if hasattr(dataset_fs, "range_event_snapshot"):
                range_events_after_prefetch, post_prefetch_ranges_complete = (
                    dataset_fs.range_event_snapshot(range_event_offset)
                )
            else:
                range_events_after_prefetch = dataset_fs.range_events(
                    since=range_event_offset
                )
                post_prefetch_ranges_complete = True
        else:
            range_events_after_prefetch = []
            post_prefetch_ranges_complete = True
        warmup_metrics_after_query = (
            dataset_fs.warmup_metrics()
            if warmup_metrics_before_query is not None else None
        )
        query_events = events[query_event_offset:]
        http_events = (
            collect_http_events(ticker.duckdb_client.connection) if trace_io else []
        )

    cache_after = cache_snapshot(cache_directory)
    if diagnostics:
        fingerprint = result_fingerprint(frame)
        if "symbol" not in frame or not frame["symbol"].eq(symbol).all():
            raise ValueError("Ticker API returned data for an unexpected symbol")
        diagnostic_data = collect_diagnostics(
            ticker, http_events, cursor_diagnostics
        )
    else:
        fingerprint = {"rows": len(frame)}
        diagnostic_data = {}

    warm_samples = []
    for trial in range(1, payload.get("warm_repeats", 0) + 1):
        warm_events = []
        warm_started_ns = time.perf_counter_ns()
        with api.capture_performance(warm_events.append):
            warm_frame = getattr(ticker, api_method)()
        warm_ended_ns = time.perf_counter_ns()
        if diagnostics and result_fingerprint(warm_frame) != fingerprint:
            raise ValueError("Warm query result differs from the cold query")
        warm_totals = _event_totals(warm_events)
        warm_samples.append({
            "trial": trial,
            "api_call_seconds": (warm_ended_ns - warm_started_ns) / 1e9,
            "execute_query_seconds": warm_totals.get(
                "duckdb.execute_query", {"seconds": 0.0}
            )["seconds"],
            "performance": warm_totals,
        })

    phase_totals = _event_totals(query_events)
    execute_query_seconds = phase_totals.get(
        "duckdb.execute_query", {"seconds": 0.0}
    )["seconds"]
    execute_attempts = phase_totals.get(
        "duckdb.execute_query", {"calls": 0}
    )["calls"]
    if diagnostics and execute_attempts < 1:
        raise ValueError("Ticker API did not emit a DuckDBClient._execute_query event")

    usage = process_usage()
    outcome = {
        "status": "ok" if len(frame) else "empty_result",
        "pid": os.getpid(),
        "symbol": symbol,
        "api_method": api_method,
        "cache_directory": str(cache_directory),
        "cache_empty_at_worker_start": True,
        "cache_before_query": cache_before,
        "data_cache_before_query": data_cache_before,
        "cache_after_query": cache_after,
        "cache_metrics_before_query": metrics_before_query,
        "cache_warmup_metrics_before_query": warmup_metrics_before_query,
        "cache_metrics_query_delta": (
            {key: metrics_after_query[key] - value
             for key, value in metrics_before_query.items()}
            if metrics_before_query is not None else None
        ),
        "cache_metrics_after_prefetch_delta": (
            {key: metrics_after_prefetch[key] - value
             for key, value in metrics_before_query.items()}
            if metrics_before_query is not None else None
        ),
        "prefetch_drain": prefetch_drain,
        "prefetch_drain_seconds": prefetch_drain_seconds,
        "range_events_after_prefetch_drain": range_events_after_prefetch,
        "range_events_after_prefetch_drain_complete": post_prefetch_ranges_complete,
        "cache_warmup_metrics_query_delta": (
            {key: warmup_metrics_after_query[key] - value
             for key, value in warmup_metrics_before_query.items()}
            if warmup_metrics_before_query is not None else None
        ),
        "import_seconds": (imported_ns - import_started_ns) / 1e9,
        "ticker_initialization_seconds": (
            ticker_initialized_ns - ticker_started_ns
        ) / 1e9,
        "connection_warmup_seconds": connection_warmup_seconds,
        "api_call_seconds": (api_ended_ns - api_started_ns) / 1e9,
        "execute_query_seconds": execute_query_seconds,
        "execute_query_attempts": execute_attempts,
        "performance": phase_totals,
        "performance_events": redact_secrets(query_events),
        "prefetch_coverage": prefetch_coverage(
            query_events, extra_ranges=range_events_after_prefetch,
            extra_ranges_complete=post_prefetch_ranges_complete,
        ),
        "initialization_performance": redact_secrets(events[:query_event_offset]),
        "metadata_prepare_performance": _event_totals(
            event for event in query_events
            if event.get("name") == "duckdb.prepare_parquet_metadata"
        ),
        "range_prefetch_performance": _event_totals(
            event for event in query_events
            if event.get("name") == "duckdb.prefetch_ranges"
        ),
        "cpu_user_seconds": usage.ru_utime,
        "cpu_system_seconds": usage.ru_stime,
        "peak_rss_bytes": usage.ru_maxrss * (1 if sys.platform in ("darwin", "win32") else 1024),
        "minor_faults": usage.ru_minflt,
        "major_faults": usage.ru_majflt,
        "result": fingerprint,
        "warm_samples": warm_samples,
        **diagnostic_data,
    }
    if ticker is not None and diagnostics:
        ticker.duckdb_client.close()
    return redact_secrets(outcome)


def run_symbol_sequence(payload, api=None):
    """Measure new-symbol cache misses after one file's footer is cached."""
    symbols = [validate_symbol(symbol) for symbol in payload["symbols"]]
    if len(symbols) < 2:
        raise ValueError("A symbol sequence needs at least two queries")
    cache_directory = Path(payload["cache_directory"])
    if not cache_directory.is_dir() or any(cache_directory.iterdir()):
        raise ValueError("worker requires an existing, empty, isolated cache directory")

    api = api or load_api_bindings()
    config = api.Configuration(
        **{**payload.get("configuration", {}),
           "cache_directory": str(cache_directory)}
    )
    ticker = api.Ticker(
        symbols[0], http_proxy=payload.get("http_proxy"),
        log_level=logging.WARNING, config=config,
    )
    client = ticker.duckdb_client
    filesystem = client._dataset_fs
    if filesystem is None:
        raise ValueError("Symbol sequence requires the dataset cache")
    if cache_snapshot(cache_directory)["files"]:
        raise ValueError("dataset cache was not empty before the first API call")
    spec = client._hf_client.dataset_spec
    hint = spec.get("footer_index", {}).get("US/stock_prices.parquet")
    if not isinstance(hint, dict):
        raise ValueError("Published stock price footer index is required")
    file_size, footer_size = hint.get("file_size"), hint.get("footer_size")
    if (type(file_size) is not int or type(footer_size) is not int
            or file_size < 12 or not 0 < footer_size <= file_size - 12):
        raise ValueError("Published stock price footer index is invalid")
    footer_start = file_size - footer_size - 8
    version = client._data_update_time
    warmup_seconds = 0.0
    warmup_bytes = payload.get("cache_connection_warmup_bytes", 0)
    if warmup_bytes:
        started_ns = time.perf_counter_ns()
        filesystem.prepare_connections(STOCK_PRICES_URL, warmup_bytes)
        warmup_seconds = (time.perf_counter_ns() - started_ns) / 1e9
    warmup_metrics = filesystem.warmup_metrics()

    samples = []
    previous_data_ranges = []
    try:
        for position, symbol in enumerate(symbols):
            current = ticker if position == 0 else api.Ticker(
                symbol, http_proxy=payload.get("http_proxy"),
                log_level=logging.WARNING, config=config,
            )
            if current.duckdb_client is not client:
                raise ValueError("Ticker instances did not reuse one DuckDB client")
            before = filesystem.metrics()
            sequence = filesystem.range_event_sequence()
            cache_before = cache_snapshot(cache_directory)
            events = []
            started_ns = time.perf_counter_ns()
            with api.capture_performance(events.append):
                frame = current.price()
            ended_ns = time.perf_counter_ns()
            after_query = filesystem.metrics()
            drain_started_ns = time.perf_counter_ns()
            drain = filesystem.await_pending()
            drain_seconds = (time.perf_counter_ns() - drain_started_ns) / 1e9
            after_drain = filesystem.metrics()
            ranges, complete = filesystem.range_event_snapshot(sequence)
            if not complete or drain["errors"]:
                raise ValueError("Range capture or background prefetch is incomplete")
            if client._data_update_time != version:
                raise ValueError("Dataset version changed during the symbol sequence")
            if frame.empty or "symbol" not in frame or not frame["symbol"].eq(symbol).all():
                raise ValueError("Ticker API returned an unexpected symbol")
            totals = _event_totals(events)
            query = totals.get("duckdb.execute_query")
            if query is None or query["calls"] != 1:
                raise ValueError("Ticker API did not emit one execute-query event")

            price_ranges = [
                event for event in ranges
                if event.get("file") == "stock_prices.parquet"
            ]
            footer_ranges = [
                event for event in price_ranges
                if event["start"] <= file_size - 1 and event["end"] >= footer_start
            ]
            data_ranges = [
                event for event in price_ranges if event["end"] < footer_start
            ]
            overlap = sum(
                max(0, min(event["end"] + 1, end) - max(event["start"], start))
                for event in data_ranges for start, end in previous_data_ranges
            )
            data_bytes = sum(event["bytes"] for event in data_ranges)
            if position == 0:
                phase = "first_file" if len(footer_ranges) == 1 and data_bytes else "invalid"
            elif footer_ranges:
                phase = "invalid"
            elif data_bytes:
                phase = "cold_data" if overlap == 0 else "invalid"
            else:
                phase = "hot_repeat" if symbol in symbols[:position] else "hot_data"
            previous_data_ranges.extend(
                (event["start"], event["end"] + 1) for event in data_ranges
            )
            samples.append({
                "position": position + 1,
                "symbol": symbol,
                "phase": phase,
                "execute_query_seconds": query["seconds"],
                "api_call_seconds": (ended_ns - started_ns) / 1e9,
                "result": result_fingerprint(frame),
                "cache_before_query": cache_before,
                "cache_after_query": cache_snapshot(cache_directory),
                "cache_metrics_query_delta": {
                    key: after_query[key] - value for key, value in before.items()
                },
                "cache_metrics_after_prefetch_delta": {
                    key: after_drain[key] - value for key, value in before.items()
                },
                "prefetch_drain": drain,
                "prefetch_drain_seconds": drain_seconds,
                "footer_range_requests": len(footer_ranges),
                "data_downloaded_bytes": data_bytes,
                "data_overlap_with_previous_downloads_bytes": overlap,
                "range_events": redact_secrets(ranges),
                "performance": totals,
            })
        return {
            "status": "ok" if all(item["phase"] != "invalid" for item in samples) else "error",
            "symbols": symbols,
            "same_client": True,
            "dataset_version": version,
            "file_size": file_size,
            "footer_size": footer_size,
            "connection_warmup_seconds": warmup_seconds,
            "warmup_metrics": warmup_metrics,
            "samples": samples,
        }
    finally:
        client.close()


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
        ROOT.parent / "defeatbeta_api" / "client" / "dataset_cache_fs.py",
        ROOT.parent / "defeatbeta_api" / "client" / "hugging_face_client.py",
        ROOT.parent / "defeatbeta_api" / "utils" / "util.py",
        ROOT.parent / "defeatbeta_api" / "data" / "ticker.py",
    )
    return {
        str(path.relative_to(ROOT.parent)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths if path.is_file()
    }


def cmd_inspect_io(args):
    """Classify a saved query trace against an identical local Parquet file."""
    import duckdb

    parquet = args.parquet.resolve()
    file_size = parquet.stat().st_size
    with parquet.open("rb") as stream:
        stream.seek(-8, os.SEEK_END)
        tail = stream.read(8)
    if len(tail) != 8 or tail[4:] != b"PAR1":
        raise ValueError("Local file has no valid Parquet footer")
    footer_size = int.from_bytes(tail[:4], "little")
    digest = hashlib.sha256()
    with parquet.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if args.expected_sha256 and digest.hexdigest() != args.expected_sha256.lower():
        raise ValueError("Local Parquet checksum does not match the expected version")

    connection = duckdb.connect(":memory:")
    try:
        chunks = connection.execute(
            "SELECT row_group_id, path_in_schema, "
            "LEAST(dictionary_page_offset, index_page_offset, data_page_offset), "
            "total_compressed_size FROM parquet_metadata(?)",
            [str(parquet)],
        ).fetchall()
    finally:
        connection.close()

    file_name = args.file_name or parquet.name
    reports = unpack_reports(json.loads(args.record.read_text(encoding="utf-8")))

    def bytes_by_kind(classified):
        totals = {}
        for event in classified:
            for piece in event["segments"]:
                kind = piece["kind"]
                totals[kind] = totals.get(kind, 0) + piece["bytes"]
        return totals

    samples = []
    for report in reports:
        for sample in report.get("samples", []):
            reads, ranges, after = sample_parquet_io_events(sample, file_name)
            if not reads and not ranges and not after:
                raise ValueError(f"No captured I/O for {file_name}")
            classified_reads = classify_parquet_io(
                reads, chunks, file_size, footer_size
            )
            classified_ranges = classify_parquet_io(
                ranges, chunks, file_size, footer_size
            )
            classified_after = classify_parquet_io(
                after, chunks, file_size, footer_size
            )
            samples.append({
                "symbol": sample.get("symbol", report.get("symbol")),
                "trial": sample.get("trial"),
                "status": sample.get("status"),
                "read_bytes_by_kind": bytes_by_kind(classified_reads),
                "range_bytes_by_kind": bytes_by_kind(classified_ranges),
                "post_query_range_bytes_by_kind": bytes_by_kind(classified_after),
                "reads": classified_reads,
                "ranges": classified_ranges,
                "post_query_ranges": classified_after,
            })
    result = {
        "file_name": file_name,
        "file_size": file_size,
        "file_sha256": digest.hexdigest(),
        "footer_size": footer_size,
        "samples": samples,
    }
    if args.pages:
        touched = {
            (piece["row_group_id"], piece["column"])
            for sample in samples
            for kind in ("reads", "ranges", "post_query_ranges")
            for event in sample[kind]
            for piece in event["segments"]
            if piece["kind"] == "column_chunk"
        }
        result["page_layout"] = inspect_parquet_pages(
            parquet, [row for row in chunks if (row[0], row[1]) in touched]
        )
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def environment_info():
    import duckdb
    import pandas
    import psutil

    connection = duckdb.connect(":memory:")
    extensions = connection.execute(
        "SELECT extension_name, installed, extension_version, install_path "
        "FROM duckdb_extensions() WHERE extension_name = 'httpfs' "
        "ORDER BY extension_name"
    ).fetchall()
    connection.close()
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
                "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()
                if installed and path and Path(path).is_file() else None,
            }
            for name, installed, version, path in extensions
        ],
    }


def cmd_run(args):
    try:
        symbols = [validate_symbol(args.symbol)] if args.symbol else list(DEFAULT_SYMBOLS)
        if args.runs < 1 or not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("runs and timeout must be positive and finite")
        if args.cache_data_memory_limit_bytes < 0:
            raise ValueError("cache memory limit must be nonnegative")
        if (args.cache_fetch_workers < 1 or args.cache_range_split_bytes < 0
                or args.cache_connection_warmup_bytes < 0):
            raise ValueError("cache network limits must be nonnegative")
        if args.cache_connection_warmup_bytes > 1024 * 1024:
            raise ValueError("connection warmup cannot exceed one MiB")
        if args.cache_connection_warmup_bytes and not args.cache:
            raise ValueError("connection warmup requires the dataset cache")
        if args.cache_connection_warmup_bytes and args.api_method != "price":
            raise ValueError("connection warmup is available only for price")
        if args.warm_repeats < 0:
            raise ValueError("warm repeats must not be negative")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", args.tag):
            raise ValueError("tag must be 1-64 filename-safe characters")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    environment = environment_info()
    implementation = source_hashes()
    configuration = {
        "duckdb_http_keep_alive": args.duckdb_http_keep_alive,
        "resolve_cdn_for_uncached_reads": args.resolve_cdn_for_uncached_reads,
        "duckdb_threads": args.duckdb_threads,
        "cache_data_memory_limit_bytes": args.cache_data_memory_limit_bytes,
        "cache_prepare_footer_on_first_use": args.cache_prepare_footer_on_first_use,
        "cache_symbol_column_chunk_prefetch": args.cache_symbol_column_chunk_prefetch,
        "cache_enabled": args.cache,
        "cache_fetch_workers": args.cache_fetch_workers,
        "cache_range_split_bytes": args.cache_range_split_bytes,
    }
    configured_settings = {
        **configuration,
        "http_proxy": redact_proxy(args.http_proxy),
    }
    if args.trace_io:
        configured_settings["trace_io"] = True
    if args.warm_repeats:
        configured_settings["warm_repeats"] = args.warm_repeats
    if args.cache_connection_warmup_bytes:
        configured_settings["cache_connection_warmup_bytes"] = (
            args.cache_connection_warmup_bytes
        )
    if args.httpfs_connection_caching is not None:
        configured_settings["httpfs_connection_caching"] = args.httpfs_connection_caching
    methodology = {
        "workload": (
            f"Ticker(symbol).{args.api_method}() through the installed "
            "defeatbeta_api package"
        ),
        "cold": (
            "Fresh worker and isolated empty cache directory per sample. Only "
            "files referenced by the query have their footers prepared; "
            "this preparation is included in the measured API call and query time."
        ),
        "main_metric": (
            "Sum of DuckDBClient._execute_query timing events emitted during "
            f"Ticker.{args.api_method}()"
        ),
        "secondary_metrics": (
            "Package import, Ticker initialization, API call, cache state, and range events"
        ),
        "excluded": "Result hashing, diagnostics, report writing, and teardown",
        "uncontrolled": "DNS, proxy state, operating-system caches, and remote CDN caches",
    }
    if args.trace_io:
        methodology["secondary_metrics"] += ", and sanitized filesystem events"
        methodology["trace_effect"] = (
            "Filesystem logging and cursor diagnostics run inside the measured query"
        )
    if args.cache_connection_warmup_bytes:
        methodology["connection_warmup"] = (
            "Transport connections are warmed with disjoint non-query ranges after "
            "Ticker initialization and before the measured API call. Warmup duration "
            "and bytes are excluded from execute_query_seconds."
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
        "url": STOCK_PRICES_URL.replace(
            "stock_prices.parquet", f"{API_FILES[args.api_method]}.parquet"
        ),
        "api_call": f"defeatbeta_api.data.ticker.Ticker.{args.api_method}",
        "resolve_cdn_for_uncached_reads": args.resolve_cdn_for_uncached_reads,
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
                cache = Path(directory) / "dataset-cache"
                cache.mkdir()
                sample = run_worker(
                    {
                        "symbol": symbol,
                        "api_method": args.api_method,
                        "cache_directory": str(cache),
                        "http_proxy": args.http_proxy,
                        "configuration": configuration,
                        "trace_io": args.trace_io,
                        "warm_repeats": args.warm_repeats,
                        "cache_connection_warmup_bytes": args.cache_connection_warmup_bytes,
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


def sequence_trials_consistent(samples, requested_runs):
    """Reject comparisons spanning dataset or result changes."""
    if len(samples) != requested_runs or any(
        sample.get("status") != "ok" for sample in samples
    ):
        return False
    signatures = {
        json.dumps({
            "dataset_version": sample.get("dataset_version"),
            "file_size": sample.get("file_size"),
            "footer_size": sample.get("footer_size"),
            "steps": [
                (step.get("symbol"), step.get("phase"), step.get("result"))
                for step in sample.get("samples", [])
            ],
        }, sort_keys=True)
        for sample in samples
    }
    return len(signatures) == 1


def cmd_sequence(args):
    try:
        symbols = [validate_symbol(item.strip()) for item in args.symbols.split(",")]
        if len(symbols) < 2 or any(not item for item in args.symbols.split(",")):
            raise ValueError("symbols must contain at least two valid entries")
        if args.runs < 1 or not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("runs and timeout must be positive and finite")
        if (args.cache_data_memory_limit_bytes < 0 or args.cache_fetch_workers < 1
                or args.cache_range_split_bytes < 0
                or not 0 <= args.cache_connection_warmup_bytes <= 1024 * 1024):
            raise ValueError("cache network settings are invalid")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", args.tag):
            raise ValueError("tag must be 1-64 filename-safe characters")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    configuration = {
        "duckdb_threads": args.duckdb_threads,
        "cache_enabled": True,
        "cache_data_memory_limit_bytes": args.cache_data_memory_limit_bytes,
        "cache_prepare_footer_on_first_use": True,
        "cache_symbol_column_chunk_prefetch": True,
        "cache_fetch_workers": args.cache_fetch_workers,
        "cache_range_split_bytes": args.cache_range_split_bytes,
    }
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run_id = f"{timestamp}_{args.tag}_{uuid.uuid4().hex[:8]}"
    path = args.output.resolve() / "local" / f"{run_id}.json"
    report = {
        "format_version": 2,
        "run_id": run_id,
        "kind": "shared_cache_symbol_sequence",
        "status": "running",
        "symbols": symbols,
        "requested_runs": args.runs,
        "primary_metric": PRIMARY_METRIC,
        "environment": environment_info(),
        "implementation": source_hashes(),
        "configured_settings": {
            **configuration,
            "cache_connection_warmup_bytes": args.cache_connection_warmup_bytes,
            "http_proxy": redact_proxy(args.http_proxy),
        },
        "methodology": {
            "workload": "Ticker(symbol).price() for each symbol in one worker and cache",
            "first_file": "Empty local cache; footer and first symbol data are cold",
            "cold_data": "Same local footer and connection; new symbol data are cold",
            "hot_data": "A new symbol reuses a locally cached row-group extent",
            "hot_repeat": "The symbol's data are already cached locally",
            "excluded": "Ticker initialization, connection warmup, result hashing, and record writing",
        },
        "samples": [],
        "statistics": None,
    }
    write_record(path, [report])
    for trial in range(1, args.runs + 1):
        print(f"[{trial}/{args.runs}] {','.join(symbols)}: starting sequence", flush=True)
        with tempfile.TemporaryDirectory(prefix="defeatbeta-api-sequence-") as directory:
            cache = Path(directory) / "dataset-cache"
            cache.mkdir()
            sample = run_worker({
                "mode": "sequence",
                "symbols": symbols,
                "cache_directory": str(cache),
                "http_proxy": args.http_proxy,
                "configuration": configuration,
                "cache_connection_warmup_bytes": args.cache_connection_warmup_bytes,
            }, args.timeout)
        sample["trial"] = trial
        report["samples"].append(sample)
        write_record(path, [report])
        if sample.get("status") == "ok":
            for step in sample["samples"]:
                print(
                    f"  {step['symbol']} {step['phase']}: "
                    f"{step['execute_query_seconds']:.6f} s, "
                    f"{step['data_downloaded_bytes']} data bytes, "
                    f"{step['footer_range_requests']} footer ranges",
                    flush=True,
                )
        else:
            print(f"  sequence {sample.get('status')}: {sample.get('error', 'invalid phase')}",
                  flush=True)

    valid = sequence_trials_consistent(report["samples"], args.runs)
    report["status"] = "complete" if valid else "invalid"
    if valid:
        report["statistics"] = [
            {
                "position": position + 1,
                "symbol": symbol,
                "phase": report["samples"][0]["samples"][position]["phase"],
                "median_seconds": statistics.median(
                    sample["samples"][position]["execute_query_seconds"]
                    for sample in report["samples"]
                ),
            }
            for position, symbol in enumerate(symbols)
        ]
    write_record(path, [report])
    print(f"Record: {path}")
    prune_local(args.output)
    return 0 if valid else 1


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


def cmd_network_cold_read(args):
    try:
        if (args.runs < 1 or not math.isfinite(args.timeout) or args.timeout <= 0
                or args.block_size < 4):
            raise ValueError("runs, timeout, and block size must be positive")
        outcome = asyncio.run(run_network_cold_read_probe(
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
            f"warm {sample['warmup_bytes_per_connection']} B x "
            f"{sample['connections']} in {sample['warmup_seconds']:.3f} s; "
            f"query {sample['chunk_size']} B chunks, "
            f"{sample['query_bytes']} B in {sample['query_seconds']:.3f} s "
            f"({sample['query_mbps']:.1f} Mbit/s)"
        )
    if args.output is not None:
        print(f"Record: {args.output}")
    return 0


def cmd_network_crossover(args):
    try:
        if (args.runs < 1 or not math.isfinite(args.timeout) or args.timeout <= 0
                or args.block_size < 1 or args.warmup_bytes < 1
                or args.warmup_bytes > args.block_size
                or args.chunk_size < 1 or args.sample_offset < 0
                or not math.isfinite(args.idle_seconds) or args.idle_seconds < 0
                or (args.heartbeat_at_seconds is not None and (
                    not math.isfinite(args.heartbeat_at_seconds)
                    or not 0 < args.heartbeat_at_seconds < args.idle_seconds
                    or args.modes != ["same"]))):
            raise ValueError("crossover runs, timeout, warmup, or chunk size is invalid")
        outcome = asyncio.run(run_network_crossover_probe(
            STOCK_PRICES_URL, args.http_proxy, args.runs, args.timeout,
            args.block_size, args.warmup_bytes, args.chunk_size,
            args.idle_seconds, args.sample_offset, tuple(args.modes),
            args.heartbeat_at_seconds,
        ))
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as handle:
                json.dump(outcome, handle, indent=2, ensure_ascii=True)
                handle.write("\n")
    except Exception as exc:
        detail = redact_secrets(str(exc))
        print(f"Error: {type(exc).__name__}: {detail}", file=sys.stderr)
        return 1
    for sample in outcome["samples"]:
        print(
            f"[{sample['trial']}/{outcome['runs_per_mode']}] {sample['mode']}: "
            f"warm {sample['warmup_bytes']} B in {sample['warmup_seconds']:.3f} s; "
            f"fresh query {sample['query_bytes']} B in "
            f"{sample['query_seconds']:.3f} s; ports "
            f"{sample['warm_ports']} -> {sample['query_ports']}"
        )
    if args.output is not None:
        print(f"Record: {args.output}")
    return 0


def cmd_network_rowgroup(args):
    try:
        if (args.runs < 1 or not math.isfinite(args.timeout) or args.timeout <= 0
                or args.group_offset < 0):
            raise ValueError("runs, timeout, and group offset must be valid")
        outcome = asyncio.run(run_rowgroup_network_probe(
            STOCK_PRICES_URL, args.http_proxy, args.runs, args.timeout,
            args.footer, args.mode_offset, args.group_offset,
        ))
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as handle:
                json.dump(outcome, handle, indent=2, ensure_ascii=True)
                handle.write("\n")
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {redact_secrets(str(exc))}",
              file=sys.stderr)
        return 1
    for sample in outcome["samples"]:
        print(
            f"[{sample['trial']}/{outcome['runs_per_mode']}] "
            f"{sample['mode']} row group {sample['row_group_id']}: "
            f"{sample['bytes']} B in {sample['wall_seconds']:.6f} s "
            f"({sample['effective_mbps']:.1f} Mbit/s)"
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
        outcome = (
            run_symbol_sequence(request) if request.get("mode") == "sequence"
            else run_api_workload(request)
        )
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
    run_parser = subparsers.add_parser("run", help="Run real Ticker API benchmark samples")
    run_parser.add_argument("--symbol")
    run_parser.add_argument("--api-method", choices=sorted(API_FILES), default="price")
    run_parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    run_parser.add_argument("--tag", default="baseline")
    run_parser.add_argument("--http-proxy")
    run_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    run_parser.add_argument("--duckdb-threads", type=int, default=4)
    run_parser.add_argument(
        "--cache-data-memory-limit-bytes", type=int, default=64 * 1024 * 1024
    )
    run_parser.add_argument(
        "--cache-prepare-footer-on-first-use", action=argparse.BooleanOptionalAction, default=True
    )
    run_parser.add_argument(
        "--cache-symbol-column-chunk-prefetch", action=argparse.BooleanOptionalAction, default=True
    )
    run_parser.add_argument("--cache-fetch-workers", type=int, default=3)
    run_parser.add_argument("--cache-range-split-bytes", type=int, default=0)
    run_parser.add_argument("--cache-connection-warmup-bytes", type=int, default=0)
    run_parser.add_argument(
        "--cache", action=argparse.BooleanOptionalAction, default=True
    )
    run_parser.add_argument("--trace-io", action="store_true")
    run_parser.add_argument(
        "--httpfs-connection-caching",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    run_parser.add_argument(
        "--duckdb-http-keep-alive", action=argparse.BooleanOptionalAction, default=True
    )
    run_parser.add_argument(
        "--resolve-cdn-for-uncached-reads", action=argparse.BooleanOptionalAction, default=True
    )
    run_parser.add_argument("--warm-repeats", type=int, default=0)
    run_parser.add_argument("--output", type=Path, default=ROOT / "results")

    sequence_parser = subparsers.add_parser(
        "sequence", help="Measure new-symbol cache misses with one shared local cache"
    )
    sequence_parser.add_argument("--symbols", default="AAPL,KDP,ZTS,KDP")
    sequence_parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    sequence_parser.add_argument("--tag", default="symbol_sequence")
    sequence_parser.add_argument("--http-proxy")
    sequence_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    sequence_parser.add_argument("--duckdb-threads", type=int, default=4)
    sequence_parser.add_argument(
        "--cache-data-memory-limit-bytes", type=int, default=64 * 1024 * 1024
    )
    sequence_parser.add_argument("--cache-fetch-workers", type=int, default=3)
    sequence_parser.add_argument("--cache-range-split-bytes", type=int, default=0)
    sequence_parser.add_argument("--cache-connection-warmup-bytes", type=int, default=0)
    sequence_parser.add_argument("--output", type=Path, default=ROOT / "results")

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

    cold_read_parser = subparsers.add_parser(
        "network-cold-read",
        help="Compare fresh and warmed independent connections for price-query bytes",
    )
    cold_read_parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    cold_read_parser.add_argument("--http-proxy")
    cold_read_parser.add_argument("--timeout", type=float, default=60.0)
    cold_read_parser.add_argument("--block-size", type=int, default=1024 * 1024)
    cold_read_parser.add_argument("--output", type=Path)

    crossover_parser = subparsers.add_parser(
        "network-crossover",
        help="Separate warm connection state from shared proxy/CDN range caches",
    )
    crossover_parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    crossover_parser.add_argument("--http-proxy")
    crossover_parser.add_argument("--timeout", type=float, default=60.0)
    crossover_parser.add_argument("--block-size", type=int, default=1024 * 1024)
    crossover_parser.add_argument("--warmup-bytes", type=int, default=1024 * 1024)
    crossover_parser.add_argument("--chunk-size", type=int, default=512 * 1024)
    crossover_parser.add_argument("--idle-seconds", type=float, default=0.0)
    crossover_parser.add_argument("--heartbeat-at-seconds", type=float)
    crossover_parser.add_argument("--sample-offset", type=int, default=0)
    crossover_parser.add_argument(
        "--modes", nargs="+", choices=("same", "other", "none"),
        default=["same", "other", "none"],
    )
    crossover_parser.add_argument("--output", type=Path)

    rowgroup_parser = subparsers.add_parser(
        "network-rowgroup",
        help="Cross single and split Range GETs over verified, disjoint row groups",
    )
    rowgroup_parser.add_argument("--footer", type=Path, required=True)
    rowgroup_parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    rowgroup_parser.add_argument("--mode-offset", type=int, choices=(0, 1, 2),
                                 default=0)
    rowgroup_parser.add_argument("--group-offset", type=int, default=0)
    rowgroup_parser.add_argument("--http-proxy")
    rowgroup_parser.add_argument("--timeout", type=float, default=60.0)
    rowgroup_parser.add_argument("--output", type=Path)

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

    inspect_parser = subparsers.add_parser(
        "inspect-io", help="Classify a saved query trace using a local Parquet file"
    )
    inspect_parser.add_argument("--record", type=Path, required=True)
    inspect_parser.add_argument("--parquet", type=Path, required=True)
    inspect_parser.add_argument("--file-name")
    inspect_parser.add_argument("--expected-sha256", required=True)
    inspect_parser.add_argument(
        "--pages", action="store_true",
        help="Inspect physical pages in column chunks touched by the trace",
    )
    return parser


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "_worker":
        return worker_main()
    args = build_parser().parse_args()
    if args.command == "run":
        return cmd_run(args)
    if args.command == "sequence":
        return cmd_sequence(args)
    if args.command == "network-probe":
        return cmd_network_probe(args)
    if args.command == "network-causality":
        return cmd_network_causality(args)
    if args.command == "network-transport":
        return cmd_network_transport(args)
    if args.command == "network-fanout":
        return cmd_network_fanout(args)
    if args.command == "network-cold-read":
        return cmd_network_cold_read(args)
    if args.command == "network-crossover":
        return cmd_network_crossover(args)
    if args.command == "network-rowgroup":
        return cmd_network_rowgroup(args)
    if args.command == "archive":
        return cmd_archive(args)
    if args.command == "inspect-io":
        return cmd_inspect_io(args)
    raise AssertionError(f"unknown command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
