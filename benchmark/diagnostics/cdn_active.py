"""Observe one CDN connection under ten minutes of regular HTTP requests."""

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import logging
from pathlib import Path
import ssl
import time
from urllib.parse import urlsplit

import certifi
import httpx

from benchmark.diagnostics.cdn_idle import h2_control_frames, pool_state, socket_state, write_report
from benchmark.diagnostics.connection_timeline import Timeline
from defeatbeta_api.client.hugging_face_client import HuggingFaceClient


INTERVAL_SECONDS = 10
DURATION_SECONDS = 600


def sample(client, url, size, timeline):
    """Issue one range GET; expose library reassignment without outer retries."""
    started = time.monotonic()
    request_offset = len(timeline.requests)
    event_offset = len(timeline.events)
    result = {"pool_before": pool_state(client, timeline), "success": False}
    try:
        response = client.get(url, headers={"Range": "bytes=0-0",
                                            "Accept-Encoding": "identity"})
        result.update(status=response.status_code, http_version=response.http_version,
                      bytes=len(response.content),
                      socket_keepalive=socket_state(response))
        result.update(Timeline.socket_details(response.extensions.get("network_stream")))
        valid = (response.status_code == 206 and len(response.content) == 1
                 and response.headers.get("Content-Range") == f"bytes 0-0/{size}"
                 and response.headers.get("Content-Encoding", "identity") == "identity")
        result["success"] = valid
        if valid:
            result["sha256"] = hashlib.sha256(response.content).hexdigest()
    except httpx.TransportError as exc:
        result["error_type"] = type(exc).__name__
    finally:
        result["seconds"] = time.monotonic() - started
        observed = timeline.requests[request_offset:]
        result["request_ids"] = [item["id"] for item in observed]
        if observed:
            for name in ("connection_id", "stream_id"):
                result[name] = observed[-1].get(name)
        result["protocol_attempts"] = [
            {key: event[key] for key in ("connection_id", "stream_id", "start_ns", "end_ns")
             if key in event}
            for event in timeline.events[event_offset:]
            if event["phase"] == "transport.protocol_until_headers"
        ]
        result["pool_after"] = pool_state(client, timeline)
    return result


def summarize(samples, events):
    valid = [item for item in samples if item["success"]]
    identities = {(item.get("connection_id"), item.get("local_port"),
                   item.get("socket_peer_host"), item.get("socket_peer_port"))
                  for item in valid}
    attempts = {item.get("connection_id") for sample_item in samples
                for item in sample_item["protocol_attempts"]}
    goaway = [item for item in events if item["phase"] == "http2.goaway_received"]
    tcp = [item for item in events if item["phase"] == "connection.connect_tcp"
           and item.get("outcome") == "complete"]
    tls = [item for item in events if item["phase"] == "connection.start_tls"
           and item.get("outcome") == "complete"]
    streams = [item.get("stream_id") for item in valid]
    same_connection = bool(samples) and (
        len(valid) == len(samples) and len(identities) == 1
        and None not in next(iter(identities)) and len(attempts) == 1
        and None not in attempts and not goaway and len(tcp) == len(tls) == 1
        and all(item["http_version"] == "HTTP/2" for item in valid)
        and all(isinstance(stream, int) for stream in streams)
        and all(after > before for before, after in zip(streams, streams[1:]))
        and len({item["sha256"] for item in valid}) == 1
    )
    return {"samples": len(samples), "valid_responses": len(valid),
            "physical_response_identities": len(identities),
            "protocol_connection_ids": sorted(value for value in attempts if value is not None),
            "tcp_connects": len(tcp), "tls_handshakes": len(tls),
            "goaway_count": len(goaway), "same_connection_throughout": same_connection,
            "observed_seconds": samples[-1]["completed_elapsed_seconds"]
            if samples else 0}


def run(output):
    if output.exists():
        raise FileExistsError("Diagnostic output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    timeline = Timeline()
    report = {
        "status": "preparing", "created_at": datetime.now(timezone.utc).isoformat(),
        "versions": {name: version(name) for name in ("httpx", "httpcore", "h2")},
        "diagnostic_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "methodology": {
            "route": "Direct HTTPS to resolved CDN hostname; verified TLS; HTTP/2",
            "range": "One byte, bytes=0-0, same file; no local data cache",
            "duration_seconds": DURATION_SECONDS, "interval_seconds": INTERVAL_SECONDS,
            "schedule": "Initial GET, then 60 GETs at deadlines after first response",
            "pool": "One connection, one retained connection, no local idle expiry",
            "keepalive": "No custom heartbeat or HTTP/2 PING; socket options read only",
            "retry": "No outer retry; existing HTTPcore reassignment remains observable",
            "privacy": "No signed URL query, response payload, headers, or error messages",
            "scope": "One origin and current network; survival gives a lower bound only",
        },
        "samples": [], "requests": timeline.requests, "events": timeline.events,
    }
    write_report(output, report)
    try:
        with ExitStack() as stack:
            resolver = HuggingFaceClient()
            stack.callback(resolver.session.close)
            signed, size = resolver.resolve_cdn_info(
                resolver.get_url_path("stock_prices"), timeout=10)
            report.update(cdn_host=urlsplit(signed).hostname, file_size=size)
            context = ssl.create_default_context(cafile=certifi.where())
            context.keylog_filename = None
            transport = httpx.HTTPTransport(
                verify=context, http2=True, trust_env=False,
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=1,
                                   keepalive_expiry=None))
            client = stack.enter_context(httpx.Client(
                transport=transport, trust_env=False, follow_redirects=False,
                timeout=httpx.Timeout(15, connect=10)))
            stack.enter_context(timeline.installed())
            stack.enter_context(h2_control_frames(timeline))
            anchor = None
            previous_end = None
            report["status"] = "running"
            for index in range(DURATION_SECONDS // INTERVAL_SECONDS + 1):
                if anchor is not None:
                    deadline = anchor + index * INTERVAL_SECONDS
                    while time.monotonic() < deadline:
                        time.sleep(min(1, deadline - time.monotonic()))
                started = time.monotonic()
                timeline.label = f"active_{index:02d}"
                observed = sample(client, signed, size, timeline)
                ended = time.monotonic()
                if anchor is None:
                    anchor = ended
                observed.update(index=index, scheduled_elapsed_seconds=index * INTERVAL_SECONDS,
                                started_elapsed_seconds=started - anchor,
                                completed_elapsed_seconds=ended - anchor,
                                actual_idle_seconds=None if previous_end is None
                                else started - previous_end)
                previous_end = ended
                report["samples"].append(observed)
                report["summary"] = summarize(report["samples"], timeline.events)
                write_report(output, report)
                print(f"sample={index} elapsed={ended - anchor:.3f} "
                      f"success={observed['success']} "
                      f"connection={observed.get('connection_id')} "
                      f"port={observed.get('local_port')} "
                      f"stream={observed.get('stream_id')} "
                      f"seconds={observed['seconds']:.3f}", flush=True)
            report["status"] = "complete"
    except BaseException as exc:
        report.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        write_report(output, report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
