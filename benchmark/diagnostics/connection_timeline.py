"""Observe unchanged API calls in an isolated diagnostic process.

Run with ``python -m benchmark.diagnostics.connection_timeline --output PATH``.
Use ``--skip-idle`` for a short capture and ``--baseline`` for an unpatched
control. These switches belong to this diagnostic, not the public API.

Spans are nested and must not be summed as exclusive time. Body timestamps
describe delivery to the application, not packet arrival or physical RTT.
Socket peers can be proxies; origin DNS and upstream TCP may then be hidden.
Private HTTPcore hooks are used only within the diagnostic context.
"""

import argparse
import ast
from contextlib import contextmanager, ExitStack, nullcontext
from contextvars import ContextVar, copy_context
from datetime import datetime, timezone
import functools
import hashlib
from importlib.metadata import version
import inspect
import json
import logging
from pathlib import Path
import re
import socket
import ssl
import sys
import tempfile
from threading import Lock
import time
import textwrap
from unittest.mock import patch
from urllib.parse import urlsplit
from weakref import WeakKeyDictionary

import httpx
import requests

from benchmark.benchmark import result_fingerprint, source_hashes


class Timeline:
    def __init__(self):
        self.zero = time.perf_counter_ns()
        self.label = "setup"
        self.events = []
        self.requests = []
        self.request_context = ContextVar("timeline_request", default=None)
        self.protocol_context = ContextVar("timeline_protocol", default=None)
        self.query_context = ContextVar("timeline_query", default=None)
        self.queries = []
        self.lock = Lock()
        self.connections = WeakKeyDictionary()
        self.connection_sequence = 0
        self.last_request_end = {}
        self.recording_ns = 0

    def now(self):
        return time.perf_counter_ns() - self.zero

    def event(self, phase, start, end, **details):
        overhead_start = time.perf_counter_ns()
        request = self.request_context.get()
        item = {
            "phase": phase, "step": self.label,
            "start_ns": start, "end_ns": end,
            "duration_ns": max(0, end - start),
            "request_id": request["id"] if request else None,
            "query_id": self.query_context.get(),
            **details,
        }
        with self.lock:
            self.events.append(item)
            self.recording_ns += time.perf_counter_ns() - overhead_start

    @contextmanager
    def query(self, **details):
        """Correlate one API call and its prefetch work without timing fingerprints."""
        with self.lock:
            item = {"id": len(self.queries) + 1, "step": self.label,
                    "start_ns": self.now(), **details}
            self.queries.append(item)
        token = self.query_context.set(item["id"])
        try:
            yield item
        except BaseException as exc:
            item["error_type"] = type(exc).__name__
            raise
        finally:
            item["end_ns"] = self.now()
            item["duration_ns"] = item["end_ns"] - item["start_ns"]
            self.query_context.reset(token)

    def query_summary(self, query):
        """Merge overlapping observed HTTP spans; remaining time is not pure CPU."""
        requests = [item for item in self.requests if item.get("query_id") == query["id"]]
        spans = sorted((max(query["start_ns"], item["start_ns"]),
                        min(query["end_ns"], item.get("end_ns", query["end_ns"])))
                       for item in requests)
        covered, end = 0, query["start_ns"]
        for start, stop in spans:
            if stop > max(start, end):
                covered += stop - max(start, end)
                end = stop
        return {"query_id": query["id"], "http_requests": len(requests),
                "observed_http_wall_seconds": covered / 1e9,
                "outside_observed_http_seconds": (query["duration_ns"] - covered) / 1e9}

    def capture_performance(self, event):
        details = {key: value for key, value in event.items()
                   if key in {"status", "cache_hit", "rows", "ranges"}
                   and isinstance(value, (str, int, float, bool))}
        self.event(event["name"], event["started_ns"] - self.zero,
                   event["ended_ns"] - self.zero, **details)

    @contextmanager
    def request(self, stack, method, url):
        parts = urlsplit(str(url))
        parent = self.request_context.get()
        with self.lock:
            item = {
                "id": len(self.requests) + 1, "step": self.label,
                "stack": stack, "method": method, "origin_host": parts.hostname,
                "file": Path(parts.path).name, "start_ns": self.now(),
                "body_bytes": 0, "body_chunks": 0,
                "parent_request_id": parent["id"] if parent else None,
                "query_id": self.query_context.get(),
            }
            self.requests.append(item)
        token = self.request_context.set(item)
        try:
            yield item
        except BaseException as exc:
            item["error_type"] = type(exc).__name__
            raise
        finally:
            item["end_ns"] = self.now()
            item["duration_ns"] = item["end_ns"] - item["start_ns"]
            connection_id = item.get("connection_id")
            if connection_id:
                self.last_request_end[connection_id] = item["end_ns"]
            self.request_context.reset(token)

    @staticmethod
    def socket_details(stream):
        details = {}
        try:
            sock = stream.get_extra_info("socket")
            if sock is not None:
                details["local_port"] = sock.getsockname()[1]
                peer = sock.getpeername()
                details["socket_peer_host"], details["socket_peer_port"] = peer[:2]
            ssl_object = stream.get_extra_info("ssl_object")
            if ssl_object is not None:
                details["alpn"] = ssl_object.selected_alpn_protocol()
                details["tls_version"] = ssl_object.version()
        except (AttributeError, OSError, IndexError):
            pass
        return details

    def trace_callback(self, request):
        pending = {}

        def record(name, info):
            phase, outcome = name.rsplit(".", 1)
            now = self.now()
            if outcome == "started":
                protocol = self.protocol_context.get()
                core_request = info.get("request")
                method = getattr(core_request, "method", None)
                if isinstance(method, bytes):
                    method = method.decode("ascii")
                details = {"method": method or request["method"]}
                if protocol:
                    details.update(protocol)
                if isinstance(info.get("stream_id"), int):
                    details["stream_id"] = info["stream_id"]
                pending[phase] = (now, details)
            elif outcome in {"complete", "failed"}:
                start, details = pending.pop(phase, (now, {}))
                self.event(phase, start, now, outcome=outcome, **details)
                if (phase.endswith("receive_response_headers")
                        and details.get("method") != "CONNECT" and outcome == "complete"):
                    request["headers_received_ns"] = now
        return record

    def wrap_span(self, owner, name, phase, *, network_only=False):
        original = getattr(owner, name)
        descriptor = inspect.getattr_static(owner, name)

        @functools.wraps(original)
        def wrapped(*args, **kwargs):
            if network_only and self.request_context.get() is None:
                return original(*args, **kwargs)
            start = self.now()
            details = {}
            try:
                result = original(*args, **kwargs)
                if phase == "transport.socket_read":
                    details["bytes"] = len(result)
                return result
            except BaseException as exc:
                details["error_type"] = type(exc).__name__
                raise
            finally:
                self.event(phase, start, self.now(), **details)

        @functools.wraps(original)
        async def async_wrapped(*args, **kwargs):
            if network_only and self.request_context.get() is None:
                return await original(*args, **kwargs)
            start = self.now()
            details = {}
            try:
                result = await original(*args, **kwargs)
                if phase == "transport.socket_read":
                    details["bytes"] = len(result)
                return result
            except BaseException as exc:
                details["error_type"] = type(exc).__name__
                raise
            finally:
                self.event(phase, start, self.now(), **details)

        if inspect.iscoroutinefunction(original):
            wrapped = async_wrapped
        replacement = staticmethod(wrapped) if isinstance(descriptor, staticmethod) else wrapped
        return patch.object(owner, name, replacement)

    @staticmethod
    def stream_acquire_location(handler):
        """Locate the request-slot acquire, excluding setup and SETTINGS changes."""
        source, first = inspect.getsourcelines(handler)
        tree = ast.parse(textwrap.dedent("".join(source)))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == "acquire"
                 and isinstance(node.func.value, ast.Attribute)
                 and node.func.value.attr == "_max_streams_semaphore"]
        if len(calls) != 2:
            raise RuntimeError("Unsupported HTTPcore stream acquisition layout")
        return handler.__code__, first + max(node.lineno for node in calls) - 1

    @contextmanager
    def installed(self):
        from concurrent.futures import ThreadPoolExecutor
        from defeatbeta_api.client import dataset_cache_fs as cache_module
        from defeatbeta_api.client.duckdb_client import capture_performance
        from defeatbeta_api.client.http_pool import ConnectionManager
        from defeatbeta_api.client.http_runtime import Connection as ManagedConnection
        from httpcore._backends.anyio import AnyIOStream
        from httpcore._backends.sync import SyncStream
        from httpcore._sync.connection_pool import PoolRequest
        from httpcore._sync.http11 import HTTP11Connection
        from httpcore._sync.http2 import HTTP2Connection
        from httpcore._synchronization import Lock as CoreLock, Semaphore

        filesystem = cache_module.DatasetCacheFileSystem
        original_send = httpx.Client.send
        original_session_send = requests.Session.send
        original_adapter_send = requests.adapters.HTTPAdapter.send
        original_submit = ThreadPoolExecutor.submit
        original_acquire = Semaphore.acquire
        original_lock_enter = CoreLock.__enter__
        original_settings = HTTP2Connection._receive_remote_settings_change
        stream_code, stream_line = self.stream_acquire_location(HTTP2Connection.handle_request)

        def acquire(semaphore):
            caller = sys._getframe(1)
            if caller.f_code is not stream_code or caller.f_lineno != stream_line:
                return original_acquire(semaphore)
            connection = caller.f_locals["self"]
            start = self.now()
            try:
                return original_acquire(semaphore)
            finally:
                self.event("transport.h2_stream_wait", start, self.now(),
                           connection_id=self.connections.get(connection),
                           effective_stream_limit=connection._max_streams,
                           peer_stream_limit=connection._h2_state.remote_settings.max_concurrent_streams)

        def lock_enter(lock):
            if self.request_context.get() is None:
                return original_lock_enter(lock)
            connection = sys._getframe(1).f_locals.get("self")
            phase = next((phase for name, phase in (
                ("_request_lock", "transport.connect_lock_wait"),
                ("_connect_lock", "transport.connect_lock_wait"),
                ("_init_lock", "transport.h2_init_lock_wait"),
                ("_read_lock", "transport.h2_read_lock_wait"),
                ("_write_lock", "transport.h2_write_lock_wait"),
            ) if getattr(connection, name, None) is lock), None)
            if phase is None:
                return original_lock_enter(lock)
            start = self.now()
            result = original_lock_enter(lock)
            self.event(phase, start, self.now(), connection_id=self.connections.get(connection))
            return result

        def settings(connection, event):
            result = original_settings(connection, event)
            now = self.now()
            self.event("transport.h2_stream_limit", now, now,
                       connection_id=self.connections.get(connection),
                       effective_stream_limit=connection._max_streams,
                       peer_stream_limit=connection._h2_state.remote_settings.max_concurrent_streams)
            return result

        @functools.wraps(original_send)
        def send(client, request, *args, **kwargs):
            with self.request("httpx", request.method, request.url) as item:
                byte_range = request.headers.get("Range", "")
                if re.fullmatch(r"bytes=\d+-\d+", byte_range):
                    item["range"] = byte_range
                sentinel = object()
                previous = request.extensions.get("trace", sentinel)
                recorder = self.trace_callback(item)

                def trace(name, info):
                    recorder(name, info)
                    if previous is not sentinel and previous is not None:
                        return previous(name, info)

                request.extensions["trace"] = trace
                try:
                    response = original_send(client, request, *args, **kwargs)
                    item.update(status=response.status_code, http_version=response.http_version)
                    item.update(self.socket_details(response.extensions.get("network_stream")))
                    return response
                finally:
                    if previous is sentinel:
                        request.extensions.pop("trace", None)
                    else:
                        request.extensions["trace"] = previous

        @functools.wraps(original_session_send)
        def session_send(session, request, *args, **kwargs):
            with self.request("requests", request.method, request.url) as item:
                response = original_session_send(session, request, *args, **kwargs)
                item["status"] = response.status_code
                return response

        @functools.wraps(original_adapter_send)
        def adapter_send(adapter, *args, **kwargs):
            start = self.now()
            response = original_adapter_send(adapter, *args, **kwargs)
            now = self.now()
            item = self.request_context.get()
            if item:
                item["headers_received_ns"] = now
            self.event("requests.adapter_until_headers", start, now)
            return response

        def body_wrapper(original):
            @functools.wraps(original)
            def iterate(response, *args, **kwargs):
                item = self.request_context.get()
                start = self.now()
                try:
                    for chunk in original(response, *args, **kwargs):
                        if item and chunk:
                            now = self.now()
                            item.setdefault("first_body_delivered_ns", now)
                            item["last_body_delivered_ns"] = now
                            item["body_bytes"] += len(chunk)
                            item["body_chunks"] += 1
                        yield chunk
                finally:
                    if item:
                        self.event("application.body_iteration", start, self.now())
            return iterate

        def protocol_wrapper(original):
            @functools.wraps(original)
            def dispatch(connection, request):
                with self.lock:
                    connection_id = self.connections.get(connection)
                    if connection_id is None:
                        self.connection_sequence += 1
                        connection_id = self.connection_sequence
                        self.connections[connection] = connection_id
                method = request.method.decode("ascii")
                item = self.request_context.get()
                if item and method != "CONNECT":
                    item["connection_id"] = connection_id
                    item["previous_request_end_ns"] = self.last_request_end.get(connection_id)
                details = {"connection_id": connection_id, "method": method}
                token = self.protocol_context.set(details)
                start = self.now()
                try:
                    response = original(connection, request)
                    details.update(self.socket_details(response.extensions.get("network_stream")))
                    if "stream_id" in response.extensions:
                        details["stream_id"] = response.extensions["stream_id"]
                        if item:
                            item["stream_id"] = response.extensions["stream_id"]
                    return response
                finally:
                    self.event("transport.protocol_until_headers", start, self.now(), **details)
                    self.protocol_context.reset(token)
            return dispatch

        def close_wrapper(original):
            @functools.wraps(original)
            def close(connection):
                now = self.now()
                expiry = getattr(connection, "_expire_at", None)
                self.event("transport.connection_close", now, now,
                           connection_id=self.connections.get(connection),
                           local_idle_expired=expiry is not None and time.monotonic() > expiry)
                return original(connection)
            return close

        @functools.wraps(original_submit)
        def submit(executor, function, *args, **kwargs):
            if getattr(function, "__name__", "") != "_fetch_block":
                return original_submit(executor, function, *args, **kwargs)
            queued = self.now()
            context = copy_context()

            def work():
                self.event("cache.worker_queue", queued, self.now())
                with capture_performance(self.capture_performance):
                    return function(*args, **kwargs)
            return original_submit(executor, context.run, work)

        with ExitStack() as stack:
            for owner, name, replacement in (
                (httpx.Client, "send", send),
                (requests.Session, "send", session_send),
                (requests.adapters.HTTPAdapter, "send", adapter_send),
                (httpx.Response, "iter_raw", body_wrapper(httpx.Response.iter_raw)),
                (requests.Response, "iter_content", body_wrapper(requests.Response.iter_content)),
                (ThreadPoolExecutor, "submit", submit),
                (Semaphore, "acquire", acquire),
                (CoreLock, "__enter__", lock_enter),
                (HTTP2Connection, "_receive_remote_settings_change", settings),
            ):
                stack.enter_context(patch.object(owner, name, replacement))
            for connection_type in (HTTP11Connection, HTTP2Connection, ManagedConnection):
                stack.enter_context(patch.object(
                    connection_type, "handle_request",
                    protocol_wrapper(connection_type.handle_request)))
                stack.enter_context(patch.object(
                    connection_type, "close", close_wrapper(connection_type.close)))
            for owner, name, phase in (
                (socket, "getaddrinfo", "transport.local_dns"),
                (socket.socket, "connect", "transport.tcp_connect"),
                (ssl.SSLSocket, "do_handshake", "transport.tls_handshake"),
                (SyncStream, "read", "transport.socket_read"),
                (SyncStream, "write", "transport.socket_write"),
                (AnyIOStream, "read", "transport.socket_read"),
                (AnyIOStream, "write", "transport.socket_write"),
                (PoolRequest, "wait_for_connection", "transport.pool_wait"),
                (ConnectionManager, "acquire", "transport.pool_wait"),
            ):
                stack.enter_context(self.wrap_span(owner, name, phase, network_only=True))
            for name in ("_fetch_block", "_read_block", "_cached_extents",
                         "_atomic_write", "_prune", "_check_response"):
                stack.enter_context(self.wrap_span(filesystem, name, "cache." + name.lstrip("_")))

            original_cache_lock = filesystem._cache_lock

            @contextmanager
            def cache_lock(instance):
                start = self.now()
                with original_cache_lock(instance):
                    acquired = self.now()
                    self.event("cache.publish_lock_wait", start, acquired)
                    try:
                        yield
                    finally:
                        self.event("cache.publish_lock_held", acquired, self.now())

            stack.enter_context(patch.object(filesystem, "_cache_lock", cache_lock))
            yield self


def run(output, *, baseline=False, skip_idle=False):
    from defeatbeta_api.client.duckdb_client import capture_performance
    from defeatbeta_api.client.duckdb_conf import Configuration
    from defeatbeta_api.data.ticker import Ticker

    timeline = Timeline()
    before = source_hashes()
    report = {
        "status": "running", "instrumented": not baseline,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "versions": {name: version(name) for name in ("httpx", "httpcore", "h2", "requests", "duckdb")},
        "implementation": before, "steps": [], "requests": timeline.requests,
        "diagnostic_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "events": timeline.events,
        "methodology": {
            "cache": "Isolated temporary directory; defaults otherwise unchanged",
            "timings": "Nested spans; application body delivery, not packet timestamps",
            "identity": "HTTPcore protocol connection ID plus local socket port and H2 stream ID",
            "proxy": "Socket peer may be a proxy; upstream DNS and TCP are not observed",
            "recording_seconds": "Time inside event appends only; not total instrumentation overhead",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError("Diagnostic output already exists")

    def save():
        output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    client = None
    try:
        with tempfile.TemporaryDirectory(prefix="defeatbeta-timeline-") as directory:
            config = Configuration(cache_directory=directory)
            hooks = nullcontext() if baseline else timeline.installed()
            with hooks, capture_performance(timeline.capture_performance):
                timeline.label = "initialize"
                start = timeline.now()
                ticker = Ticker("AAPL", config=config, log_level=logging.WARNING)
                client = ticker.duckdb_client
                filesystem = client._dataset_fs
                initial_version = client._data_update_time
                report["dataset_version"] = initial_version
                report["steps"].append({"label": "initialize", "start_ns": start,
                                        "end_ns": timeline.now()})

                def call(symbol, api_method, idle=0):
                    timeline.label = f"{symbol}.{api_method}.idle{idle}"
                    current = Ticker(symbol, config=config, log_level=logging.WARNING)
                    if current.duckdb_client is not client:
                        raise RuntimeError("Ticker did not reuse the shared client")
                    metrics = filesystem.metrics()
                    request_offset = len(timeline.requests)
                    sequence = filesystem.range_event_sequence()
                    start = timeline.now()
                    frame = getattr(current, api_method)()
                    end = timeline.now()
                    drain = filesystem.await_pending()
                    after = filesystem.metrics()
                    ranges, complete = filesystem.range_event_snapshot(sequence)
                    if drain["errors"] or not complete:
                        raise RuntimeError("Range observation was incomplete")
                    report["steps"].append({
                        "label": timeline.label, "symbol": symbol, "api_method": api_method,
                        "requested_idle_seconds": idle, "same_client": True,
                        "start_ns": start, "end_ns": end, "seconds": (end - start) / 1e9,
                        "request_ids": [item["id"] for item in timeline.requests[request_offset:]],
                        "cache_delta": {key: after[key] - value for key, value in metrics.items()},
                        "ranges": ranges, "result": result_fingerprint(frame),
                        "footer_mtimes_ns": {path.name: path.stat().st_mtime_ns
                                             for path in Path(directory).glob("*.footer")},
                    })
                    if client._data_update_time != initial_version:
                        raise RuntimeError("Dataset version changed during the diagnostic")
                    print(f"{timeline.label}: {(end - start) / 1e9:.6f} s, "
                          f"{after['downloaded_bytes'] - metrics['downloaded_bytes']} bytes", flush=True)
                    save()

                for symbol, api_method in (
                    ("AAPL", "price"), ("KDP", "price"), ("ZTS", "price"),
                    ("MSFT", "info"), ("AAPL", "calendar"),
                    ("NVDA", "info"), ("KDP", "calendar"),
                ):
                    call(symbol, api_method)
                if not skip_idle:
                    for idle, symbol in ((30, "MSFT"), (90, "NVDA"), (150, "TSLA")):
                        timeline.label = f"idle{idle}"
                        print(f"Waiting {idle} seconds before {symbol}.price", flush=True)
                        deadline = time.monotonic() + idle
                        while time.monotonic() < deadline:
                            time.sleep(min(30, max(0, deadline - time.monotonic())))
                            print(f"Idle {idle}: {max(0, deadline - time.monotonic()):.0f} seconds remaining",
                                  flush=True)
                        call(symbol, "price", idle)
                call("KDP", "price")
                timeline.label = "teardown"
                client.close()
                client = None
        report["status"] = "complete" if source_hashes() == before else "invalid_source_changed"
    except Exception as exc:
        report["status"] = "error"
        report["error_type"] = type(exc).__name__
        raise
    finally:
        if client is not None:
            client.close()
        report["event_append_seconds"] = timeline.recording_ns / 1e9
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--skip-idle", action="store_true")
    args = parser.parse_args()
    report = run(args.output, baseline=args.baseline, skip_idle=args.skip_idle)
    print(f"Record: {args.output}")
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
