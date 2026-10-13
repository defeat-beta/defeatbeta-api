"""Compare direct and proxied CDN reuse without changing production policy.

Run in a fresh process. Profiles are diagnostic controls, not API settings.
No HTTP heartbeat is sent during idle intervals. TCP keepalive is enabled on
the observed socket after each response so proxy socket-option propagation
cannot silently turn an enabled control into a disabled control.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import logging
from pathlib import Path
import re
import socket
import time
from urllib.parse import urlsplit
from urllib.request import getproxies, proxy_bypass
from unittest.mock import patch

import httpx

from benchmark.diagnostics.connection_timeline import Timeline
from defeatbeta_api.client.hugging_face_client import HuggingFaceClient


@contextmanager
def h2_control_frames(timeline):
    """Record control-frame events without changing HTTPcore event handling."""
    import h2.events
    from httpcore._sync.http2 import HTTP2Connection

    original = HTTP2Connection._read_incoming_data

    def read(connection, request):
        events = original(connection, request)
        for event in events:
            if isinstance(event, h2.events.ConnectionTerminated):
                now = timeline.now()
                timeline.event("http2.goaway_received", now, now,
                               connection_id=timeline.connections.get(connection),
                               error_code=int(event.error_code),
                               last_stream_id=event.last_stream_id)
            elif isinstance(event, (h2.events.PingReceived, h2.events.PingAckReceived)):
                now = timeline.now()
                timeline.event("http2.ping_received", now, now,
                               connection_id=timeline.connections.get(connection),
                               acknowledgement=isinstance(event, h2.events.PingAckReceived))
        return events

    with patch.object(HTTP2Connection, "_read_incoming_data", read):
        yield


def keepalive_options():
    """Use a 30-second idle probe, then 10-second intervals and three probes."""
    options = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1, "enabled")]
    idle = getattr(socket, "TCP_KEEPIDLE", getattr(socket, "TCP_KEEPALIVE", None))
    if idle is not None:
        options.append((socket.IPPROTO_TCP, idle, 30, "idle_seconds"))
    for name, value, label in (("TCP_KEEPINTVL", 10, "interval_seconds"),
                               ("TCP_KEEPCNT", 3, "probe_count")):
        option = getattr(socket, name, None)
        if option is not None:
            options.append((socket.IPPROTO_TCP, option, value, label))
    return options


def socket_state(response, enable_keepalive=False):
    stream = response.extensions.get("network_stream")
    sock = stream.get_extra_info("socket") if stream is not None else None
    if sock is None:
        return {"observed": False}
    result = {"observed": True, "applied_after_response": enable_keepalive}
    for level, option, desired, label in keepalive_options():
        try:
            if enable_keepalive:
                sock.setsockopt(level, option, desired)
            actual = sock.getsockopt(level, option)
            result[label] = bool(actual) if label == "enabled" else actual
        except OSError as exc:
            result[label + "_error_type"] = type(exc).__name__
    return result


def pool_state(client, timeline):
    """Observe private HTTPcore state without polling the socket or reading it."""
    pool = getattr(client._transport, "_pool", None)
    states = []
    for connection in getattr(pool, "connections", ()):
        protocol = getattr(connection, "_connection", None)
        # A CONNECT tunnel wraps an HTTPConnection before its first request.
        nested = getattr(protocol, "_connection", None)
        if nested is not None:
            protocol = nested
        expiry = getattr(protocol, "_expire_at", None)
        termination = getattr(protocol, "_connection_terminated", None)
        states.append({
            "connection_id": timeline.connections.get(protocol) if protocol is not None else None,
            "idle": connection.is_idle(), "closed": connection.is_closed(),
            "available": connection.is_available(),
            "local_idle_expired": expiry is not None and time.monotonic() > expiry,
            "read_error_type": type(protocol._read_exception).__name__
            if getattr(protocol, "_read_exception", None) is not None else None,
            "goaway_error_code": getattr(termination, "error_code", None),
        })
    return states


def sample(client, url, profile, timeline, *, previous_end=None):
    start = time.monotonic()
    result = {
        "profile": profile, "actual_idle_seconds": None if previous_end is None
        else start - previous_end, "pool_before": pool_state(client, timeline),
        "attempts": [],
    }
    for attempt in range(2):
        observed = {}

        def trace(name, info):
            current = timeline.request_context.get()
            if current is not None:
                current["profile"] = profile
                observed["request_id"] = current["id"]
            if name.endswith(".failed"):
                observed.setdefault("transport_failures", []).append({
                    "phase": name.rsplit(".", 1)[0],
                    "error_type": type(info.get("exception")).__name__,
                })

        request = client.build_request(
            "GET", url, headers={"Range": "bytes=0-65535",
                                 "Accept-Encoding": "identity"},
            extensions={"trace": trace},
        )
        attempt_start = time.monotonic()
        try:
            response = client.send(request)
            observed.update(status=response.status_code, http_version=response.http_version,
                            bytes=len(response.content))
            valid = (response.status_code == 206 and len(response.content) == 65536
                     and re.fullmatch(r"bytes 0-65535/\d+",
                                      response.headers.get("Content-Range", "")) is not None
                     and response.headers.get("Content-Encoding", "identity") == "identity")
            observed["valid_range"] = valid
            if valid:
                observed["sha256"] = hashlib.sha256(response.content).hexdigest()
            observed["socket_keepalive"] = socket_state(
                response, enable_keepalive=profile.endswith("tcp_keepalive"))
            observed.update(Timeline.socket_details(response.extensions.get("network_stream")))
            result["success"] = valid
        except httpx.TransportError as exc:
            observed["error_type"] = type(exc).__name__
            result["success"] = False
        finally:
            observed["seconds"] = time.monotonic() - attempt_start
            result["attempts"].append(observed)
        if "error_type" not in observed or attempt == 1:
            break
    result["seconds"] = time.monotonic() - start
    result["pool_after"] = pool_state(client, timeline)
    return result, time.monotonic()


def write_report(path, report):
    serialized = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
    if re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", serialized):
        raise ValueError("Diagnostic reports must contain English text only")
    path.write_text(serialized, encoding="utf-8")


def run(output, idle_intervals=(30, 90, 150)):
    if not idle_intervals or any(interval <= 0 for interval in idle_intervals):
        raise ValueError("Idle intervals must be positive")
    if output.exists():
        raise FileExistsError("Diagnostic output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    timeline = Timeline()
    report = {
        "status": "running", "created_at": datetime.now(timezone.utc).isoformat(),
        "versions": {name: version(name) for name in ("httpx", "httpcore", "h2")},
        "diagnostic_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "methodology": {
            "range": "Same 64 KiB range; no local file cache",
            "profiles": "Direct/proxy crossed with expiry120, unlimited, TCP keepalive",
            "tcp_keepalive": "Applied to the observed socket after response; read back",
            "idle": "No application heartbeat; actual per-client idle recorded",
            "retry": "At most two sends per sample, matching the cache range retry count",
            "limits": "Three connections and three keepalive slots per profile",
            "scope": "One CDN and one current route; not a universal timeout or throughput test",
            "privacy": "No signed URL query, credentials, headers, payload, or error messages",
        },
        "steps": [], "requests": timeline.requests, "events": timeline.events,
    }
    try:
        with ExitStack() as stack:
            resolver = HuggingFaceClient()
            stack.callback(resolver.session.close)
            signed, size = resolver.resolve_cdn_info(
                resolver.get_url_path("stock_prices"), timeout=10)
            host = urlsplit(signed).hostname
            report.update(cdn_host=host, file_size=size)
            proxies = getproxies()
            proxy = proxies.get("https") or proxies.get("all")
            if not proxy or proxy_bypass(host):
                raise RuntimeError("An applicable environment proxy is required for comparison")
            proxy_parts = urlsplit(proxy)
            report["proxy"] = {"scheme": proxy_parts.scheme, "host": proxy_parts.hostname,
                               "port": proxy_parts.port}
            clients = {}
            for route in ("direct", "proxy"):
                for policy, expiry in (("expiry120", 120), ("unlimited", None),
                                       ("tcp_keepalive", None)):
                    transport = httpx.HTTPTransport(
                        http2=True, trust_env=False, proxy=proxy if route == "proxy" else None,
                        limits=httpx.Limits(max_connections=3, max_keepalive_connections=3,
                                           keepalive_expiry=expiry),
                    )
                    clients[route + "." + policy] = stack.enter_context(httpx.Client(
                        transport=transport, trust_env=False,
                        timeout=httpx.Timeout(15, connect=10),
                    ))
            stack.enter_context(timeline.installed())
            stack.enter_context(h2_control_frames(timeline))
            previous = {}
            with ThreadPoolExecutor(max_workers=len(clients)) as executor:
                for idle in (0, *idle_intervals):
                    timeline.label = "idle" + str(idle)
                    if idle:
                        print(json.dumps({"stage": "waiting", "idle_seconds": idle}), flush=True)
                        time.sleep(idle)
                    futures = {
                        name: executor.submit(sample, client, signed, name, timeline,
                                              previous_end=previous.get(name))
                        for name, client in clients.items()
                    }
                    samples = []
                    for name, future in futures.items():
                        observed, previous[name] = future.result()
                        samples.append(observed)
                        print(json.dumps({"idle": idle, "profile": name,
                                          "success": observed["success"],
                                          "seconds": round(observed["seconds"], 3),
                                          "attempts": len(observed["attempts"])}), flush=True)
                    report["steps"].append({"requested_idle_seconds": idle, "samples": samples})
                    write_report(output, report)
            report["status"] = "complete"
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        write_report(output, report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--idle-seconds", type=int, nargs="+", default=[30, 90, 150],
                        help="Diagnostic idle intervals; default: 30 90 150")
    arguments = parser.parse_args()
    run(arguments.output, arguments.idle_seconds)
