"""Capture OS TCP keepalive and passive HTTP/2 retirement on two direct sockets.

macOS only. No HTTP request or PING is sent during the idle observation. The
HTTPX transport configures socket options before use; HTTPcore retains control
of TLS and HTTP/2. The password is read with getpass and sent only to sudo stdin.
Capture is limited to two reserved source ports and one CDN IPv4 address.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
import csv
from datetime import datetime, timezone
import getpass
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import select
import signal
import socket
import ssl
import subprocess
import time
from unittest.mock import patch
from urllib.parse import urlsplit

import certifi
import httpcore
import httpx
import psutil

from benchmark.diagnostics.cdn_idle import h2_control_frames, keepalive_options, sample, write_report
from benchmark.diagnostics.connection_timeline import Timeline
from defeatbeta_api.client.hugging_face_client import HuggingFaceClient


TSHARK = "/Applications/Wireshark.app/Contents/MacOS/tshark"
IDLE_SECONDS = 95
PACKET_FIELDS = (
    "frame.number", "frame.time_epoch", "frame.len", "ip.src", "ip.dst",
    "tcp.srcport", "tcp.dstport", "tcp.seq_raw", "tcp.ack_raw", "tcp.len",
    "tcp.flags", "tcp.flags.fin", "tcp.flags.reset", "tcp.flags.ack",
    "tcp.analysis.keep_alive", "tcp.analysis.keep_alive_ack", "tcp.stream",
)


@contextmanager
def reserved_connections(host, ipv4, sockets, profile_context):
    """Bind capture scope before connecting, without replacing TLS or HTTP."""
    original = socket.create_connection
    unused = dict(sockets)

    def connect(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None,
                *, all_errors=False):
        profile = profile_context.get()
        if address == (host, 443) and profile in unused:
            sock = unused.pop(profile)
            sock.settimeout(timeout)
            sock.connect((ipv4, 443))
            return sock
        return original(address, timeout, source_address, all_errors=all_errors)

    with patch.object(socket, "create_connection", connect):
        yield


def capture_arguments(ipv4, ports, output, interface="en0"):
    # All arguments are passed without a shell. The alarm bounds orphaned capture.
    socket.inet_pton(socket.AF_INET, ipv4)
    if len(ports) != 2 or any(type(port) is not int or not 0 < port < 65536 for port in ports):
        raise ValueError("Two valid reserved ports are required")
    if re.fullmatch(r"[A-Za-z0-9_.:-]+", interface) is None:
        raise ValueError("Invalid capture interface")
    capture_filter = f"tcp and host {ipv4} and port 443 and (port {ports[0]} or port {ports[1]})"
    return [
        "sudo", "-S", "-p", "", "/usr/bin/perl", "-e", "alarm 120; exec @ARGV",
        "/usr/sbin/tcpdump", "-i", interface, "-p", "-B", "4096", "-n", "-U", "-s", "128",
        "-c", "2000", "-Z", getpass.getuser(), "-w", str(output), capture_filter,
    ]


def capture_quality(text):
    snapshot = re.search(r"snapshot length (\d+) bytes", text)
    dropped = re.search(r"(\d+) packets dropped by kernel", text)
    captured = re.search(r"(\d+) packets captured", text)
    result = {
        "actual_snapshot_bytes": int(snapshot[1]) if snapshot else None,
        "dropped_packets": int(dropped[1]) if dropped else None,
        "captured_packets": int(captured[1]) if captured else None,
    }
    result["within_requested_limits"] = (
        result["actual_snapshot_bytes"] == 128 and result["dropped_packets"] == 0
        and result["captured_packets"] is not None
    )
    return result


def find_capture_process(output):
    for process in psutil.process_iter(["name", "cmdline", "uids"]):
        try:
            info = process.info
            if (info["name"] == "tcpdump" and str(output) in (info["cmdline"] or [])
                    and info["uids"] is not None and info["uids"].effective == os.getuid()):
                return process
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def passive_read(client, url, profile, timeline, deadline):
    """Decode incoming HTTP/2 frames without writing application traffic."""
    protocol = client._transport._pool.connections[0]._connection
    sock = protocol._network_stream.get_extra_info("socket")
    request = httpcore.Request("GET", url, extensions={"timeout": {"read": 5}})
    result = {"profile": profile, "events": []}
    with timeline.request("passive_http2", "READ", url) as observed:
        observed["profile"] = profile
        while time.monotonic() < deadline:
            pending = sock.pending() if hasattr(sock, "pending") else 0
            ready = select.select([sock], [], [], min(1, max(0, deadline - time.monotonic())))[0]
            if not ready and not pending:
                continue
            try:
                events = protocol._read_incoming_data(request)
                for event in events:
                    item = {"type": type(event).__name__, "decoded_ns": timeline.now()}
                    if type(event).__name__ == "ConnectionTerminated":
                        item.update(error_code=int(event.error_code), last_stream_id=event.last_stream_id)
                    result["events"].append(item)
            except Exception as exc:
                result.update(ended_ns=timeline.now(), read_error_type=type(exc).__name__)
                break
    return result


def decode_packets(path):
    command = [TSHARK, "-2", "-n", "-r", str(path), "-T", "fields",
               "-E", "header=y", "-E", "separator=,", "-E", "quote=d"]
    for name in PACKET_FIELDS:
        command.extend(["-e", name])
    decoded = subprocess.run(command, capture_output=True, text=True, check=True)
    return list(csv.DictReader(io.StringIO(decoded.stdout)))


def run(output):
    if output.exists():
        raise FileExistsError("Capture output directory already exists")
    output.mkdir(parents=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    report_path = output / "report.json"
    packet_path = output / "packets.pcapng"
    log_path = output / "capture.log"
    timeline = Timeline()
    report = {
        "status": "preparing", "created_at": datetime.now(timezone.utc).isoformat(),
        "epoch_zero_ns": time.time_ns() - timeline.now(),
        "diagnostic_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "methodology": {
            "idle_seconds": IDLE_SECONDS, "route": "Direct HTTPS, fixed CDN IPv4",
            "capture": "Two reserved source ports; packet headers plus encrypted TLS prefix",
            "limits": "128-byte snapshots, 2000 packets, 120-second OS alarm",
            "credentials": "getpass to sudo stdin only; no credential in arguments or report",
            "tls": "Certificate verification retained; no TLS key log or decryption",
            "idle_traffic": "No application request, HTTP/2 PING, or custom heartbeat",
            "passive_read": "Incoming frames decoded without calling HTTPcore write methods",
        },
        "profiles": {}, "initial": [], "passive": [],
        "requests": timeline.requests, "events": timeline.events,
    }
    capture = None
    helper = None
    try:
        with ExitStack() as stack:
            resolver = HuggingFaceClient()
            stack.callback(resolver.session.close)
            signed, size = resolver.resolve_cdn_info(resolver.get_url_path("stock_prices"), timeout=10)
            host = urlsplit(signed).hostname
            ipv4 = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
            report.update(cdn_host=host, cdn_ipv4=ipv4, file_size=size)
            route = subprocess.run(["/sbin/route", "-n", "get", ipv4],
                                   capture_output=True, text=True, check=True)
            match = re.search(r"^\s*interface:\s*(\S+)", route.stdout, re.MULTILINE)
            if match is None:
                raise RuntimeError("CDN route has no observable interface")
            report["capture_interface"] = match[1]
            sockets = {}
            clients = {}
            for enabled in (False, True):
                profile = "direct.os_enabled" if enabled else "direct.os_disabled"
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                stack.callback(sock.close)
                sock.bind(("", 0))
                sockets[profile] = sock
                report["profiles"][profile] = {"local_port": sock.getsockname()[1], "enabled": enabled}
                context = ssl.create_default_context(cafile=certifi.where())
                context.keylog_filename = None
                options = [(level, option, value) for level, option, value, label in keepalive_options()]
                if not enabled:
                    options = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 0)]
                transport = httpx.HTTPTransport(
                    verify=context, http2=True, trust_env=False, socket_options=options,
                    limits=httpx.Limits(max_connections=1, max_keepalive_connections=1,
                                       keepalive_expiry=None),
                )
                clients[profile] = stack.enter_context(httpx.Client(
                    transport=transport, trust_env=False, timeout=15))
            arguments = capture_arguments(ipv4, [s.getsockname()[1] for s in sockets.values()],
                                          packet_path, interface=report["capture_interface"])
            report["capture_filter"] = arguments[-1]
            write_report(report_path, report)
            print(json.dumps({"stage": "prepared", "cdn": host, "ipv4": ipv4,
                              "profiles": report["profiles"], "capture_filter": arguments[-1]}), flush=True)
            password = getpass.getpass("Administrator password (not echoed): ")
            capture_log = stack.enter_context(log_path.open("wb"))
            helper = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                      stderr=capture_log, env={**os.environ, "LC_ALL": "C"})
            helper.stdin.write((password + "\n").encode())
            helper.stdin.flush()
            helper.stdin.close()
            del password
            startup = time.monotonic()
            while time.monotonic() - startup < 10:
                capture = find_capture_process(packet_path)
                if capture is not None and "listening on" in log_path.read_text(errors="replace"):
                    break
                if helper.poll() is not None:
                    raise RuntimeError("Packet capture failed to start")
                time.sleep(0.1)
            else:
                raise RuntimeError("Packet capture did not become ready")
            report["capture_uid"] = capture.uids().effective
            print(json.dumps({"stage": "capture_ready", "uid": report["capture_uid"]}), flush=True)
            profile_context = ContextVar("capture_profile", default=None)
            stack.enter_context(reserved_connections(host, ipv4, sockets, profile_context))
            stack.enter_context(timeline.installed())
            stack.enter_context(h2_control_frames(timeline))

            def initial(profile):
                token = profile_context.set(profile)
                try:
                    value, ended = sample(clients[profile], signed, profile, timeline)
                    if (not value["success"] or value["attempts"][-1]["http_version"] != "HTTP/2"
                            or value["attempts"][-1].get("local_port") != report["profiles"][profile]["local_port"]):
                        raise RuntimeError("Initial request did not use the reserved HTTP/2 socket")
                    return value
                finally:
                    profile_context.reset(token)

            with ThreadPoolExecutor(max_workers=2) as executor:
                timeline.label = "initialize"
                report["initial"] = list(executor.map(initial, clients))
                report["status"] = "observing"
                timeline.label = "passive_idle"
                report["idle_started_ns"] = timeline.now()
                deadline = time.monotonic() + IDLE_SECONDS
                futures = [executor.submit(passive_read, client, signed, profile, timeline, deadline)
                           for profile, client in clients.items()]
                write_report(report_path, report)
                print(json.dumps({"stage": "observing", "idle_seconds": IDLE_SECONDS,
                                  "sockets": [r["attempts"][-1]["socket_keepalive"]
                                              for r in report["initial"]]}), flush=True)
                report["passive"] = [future.result(timeout=IDLE_SECONDS + 10) for future in futures]
                if deadline > time.monotonic():
                    time.sleep(deadline - time.monotonic())
            capture.send_signal(signal.SIGINT)
            helper.wait(timeout=10)
            report["capture_quality"] = capture_quality(log_path.read_text())
            report["packets"] = decode_packets(packet_path)
            report["status"] = "complete" if report["capture_quality"]["within_requested_limits"] \
                else "complete_with_capture_limits"
            print(json.dumps({"stage": "complete", "packets": len(report["packets"]),
                              "passive": report["passive"]}), flush=True)
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        if capture is not None:
            try:
                if capture.is_running():
                    capture.send_signal(signal.SIGINT)
            except psutil.NoSuchProcess:
                pass
        if helper is not None:
            helper.wait(timeout=15)
        write_report(report_path, report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
