"""Verify idle diagnostics against real sockets and controlled failures."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx

from benchmark.diagnostics.cdn_idle import h2_control_frames, pool_state, sample, write_report
from benchmark.diagnostics.connection_timeline import Timeline


@contextmanager
def range_server():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            self.send_response(206)
            self.send_header("Content-Length", "65536")
            self.send_header("Content-Range", "bytes 0-65535/131072")
            self.end_headers()
            self.wfile.write(b"x" * 65536)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/object?Signature=do-not-save"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class TestCdnIdle(unittest.TestCase):
    def test_control_frames_preserve_events_and_omit_debug_payload(self):
        import h2.events
        from httpcore._sync.http2 import HTTP2Connection

        goaway = h2.events.ConnectionTerminated()
        goaway.error_code = 0
        goaway.last_stream_id = 3
        goaway.additional_data = b"Signature=do-not-save"
        ping = h2.events.PingAckReceived(ping_data=b"secret!!")
        events = [goaway, ping]
        connection = object.__new__(HTTP2Connection)
        timeline = Timeline()
        timeline.connections[connection] = 1
        with patch.object(HTTP2Connection, "_read_incoming_data", return_value=events):
            original = HTTP2Connection._read_incoming_data
            with h2_control_frames(timeline):
                observed = connection._read_incoming_data(None)
            self.assertIs(HTTP2Connection._read_incoming_data, original)
        self.assertIs(observed, events)
        self.assertEqual(timeline.events[0]["error_code"], 0)
        self.assertEqual(timeline.events[0]["last_stream_id"], 3)
        self.assertTrue(timeline.events[1]["acknowledgement"])
        serialized = json.dumps(timeline.events)
        self.assertNotIn("do-not-save", serialized)
        self.assertNotIn("secret!!", serialized)

    def test_control_frame_hook_is_restored_after_error(self):
        from httpcore._sync.http2 import HTTP2Connection

        failure = httpx.ReadError("Signature=do-not-save")
        with patch.object(HTTP2Connection, "_read_incoming_data", side_effect=failure):
            original = HTTP2Connection._read_incoming_data
            with self.assertRaises(httpx.ReadError) as raised:
                with h2_control_frames(Timeline()):
                    object.__new__(HTTP2Connection)._read_incoming_data(None)
            self.assertIs(HTTP2Connection._read_incoming_data, original)
            self.assertIs(raised.exception, failure)

    def test_same_socket_is_reused_and_keepalive_is_read_back(self):
        timeline = Timeline()
        with range_server() as url, timeline.installed(), httpx.Client(
                trust_env=False, limits=httpx.Limits(keepalive_expiry=None)) as client:
            first, ended = sample(client, url, "direct.tcp_keepalive", timeline)
            second, _ = sample(client, url, "direct.tcp_keepalive", timeline, previous_end=ended)
            self.assertTrue(first["success"] and second["success"])
            self.assertTrue(first["attempts"][0]["socket_keepalive"]["enabled"])
            self.assertEqual(first["attempts"][0]["local_port"], second["attempts"][0]["local_port"])
            self.assertEqual(timeline.requests[0]["connection_id"], timeline.requests[1]["connection_id"])
            self.assertEqual(second["pool_before"][0]["connection_id"], timeline.requests[0]["connection_id"])
            self.assertFalse(second["pool_before"][0]["local_idle_expired"])
            self.assertGreaterEqual(second["actual_idle_seconds"], 0)
        self.assertNotIn("do-not-save", json.dumps([first, second, timeline.requests, timeline.events]))

    def test_local_expiry_is_distinguished_from_peer_close(self):
        timeline = Timeline()
        with range_server() as url, timeline.installed(), httpx.Client(
                trust_env=False, limits=httpx.Limits(keepalive_expiry=0.05)) as client:
            first, ended = sample(client, url, "direct.expiry120", timeline)
            time.sleep(0.08)
            second, _ = sample(client, url, "direct.expiry120", timeline, previous_end=ended)
            self.assertTrue(first["success"] and second["success"])
            self.assertTrue(second["pool_before"][0]["local_idle_expired"])
            self.assertNotEqual(timeline.requests[0]["connection_id"], timeline.requests[1]["connection_id"])

    def test_transport_failure_is_retried_and_error_messages_are_omitted(self):
        attempts = []

        def respond(request):
            attempts.append(request)
            if len(attempts) == 1:
                raise httpx.ReadError("Signature=do-not-save")
            return httpx.Response(206, content=b"x" * 65536,
                                  headers={"Content-Range": "bytes 0-65535/131072"})

        timeline = Timeline()
        with timeline.installed(), httpx.Client(transport=httpx.MockTransport(respond)) as client:
            result, _ = sample(client, "https://example.test/object?Signature=do-not-save",
                               "direct.unlimited", timeline)
        self.assertTrue(result["success"])
        self.assertEqual(len(result["attempts"]), 2)
        self.assertEqual(result["attempts"][0]["error_type"], "ReadError")
        self.assertNotIn("do-not-save", json.dumps([result, timeline.requests, timeline.events]))

    def test_wrong_byte_range_is_not_reported_as_success(self):
        timeline = Timeline()
        transport = httpx.MockTransport(lambda request: httpx.Response(
            206, content=b"x" * 65536, headers={"Content-Range": "bytes 1-65536/131072"}))
        with timeline.installed(), httpx.Client(transport=transport) as client:
            result, _ = sample(client, "https://example.test/object", "direct.unlimited", timeline)
        self.assertFalse(result["success"])
        self.assertNotIn("sha256", result["attempts"][0])
        self.assertEqual(len(result["attempts"]), 1)

    def test_failed_connect_has_no_protocol_identity(self):
        connection = SimpleNamespace(_connection=None, is_idle=lambda: False,
                                     is_closed=lambda: True, is_available=lambda: False)
        client = SimpleNamespace(_transport=SimpleNamespace(
            _pool=SimpleNamespace(connections=[connection])))
        result = pool_state(client, Timeline())
        self.assertIsNone(result[0]["connection_id"])
        self.assertTrue(result[0]["closed"])

    def test_report_has_ascii_content_and_real_newlines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            write_report(path, {"status": "complete", "steps": []})
            content = path.read_text()
            self.assertTrue(content.isascii())
            self.assertEqual(json.loads(content)["status"], "complete")
            self.assertTrue(content.endswith("\n"))
