"""Verify passive capture isolation, startup observations, and hook recovery."""

from contextvars import ContextVar
import json
import os
from pathlib import Path
import socket
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import h2.events
import httpcore

from benchmark.diagnostics.connection_timeline import Timeline
from benchmark.diagnostics.tcp_keepalive_capture import (
    capture_arguments, capture_quality, find_capture_process, passive_read, reserved_connections,
)


class TestTcpKeepaliveCapture(unittest.TestCase):
    def test_actual_capture_limits_are_observed_not_assumed(self):
        text = ("tcpdump: WARNING: snaplen raised from 128 to 524288\n"
                "tcpdump: listening on pktap,all, snapshot length 524288 bytes\n"
                "228 packets captured\n24833 packets received by filter\n"
                "159 packets dropped by kernel\n")
        quality = capture_quality(text)
        self.assertEqual(quality["actual_snapshot_bytes"], 524288)
        self.assertEqual(quality["dropped_packets"], 159)
        self.assertFalse(quality["within_requested_limits"])

    def test_clean_capture_quality_requires_observed_counts(self):
        text = ("tcpdump: listening on en0, snapshot length 128 bytes\n"
                "200 packets captured\n200 packets received by filter\n"
                "0 packets dropped by kernel\n")
        self.assertTrue(capture_quality(text)["within_requested_limits"])
        self.assertFalse(capture_quality("")["within_requested_limits"])

    def test_passive_reader_never_sends_heartbeat_or_http_request(self):
        event = h2.events.ConnectionTerminated()
        event.error_code = 0
        event.last_stream_id = 1
        event.additional_data = b"Signature=do-not-save"
        sock = Mock()
        sock.pending.return_value = 0
        protocol = Mock()
        protocol._network_stream.get_extra_info.return_value = sock
        protocol._read_incoming_data.side_effect = [[event], httpcore.RemoteProtocolError("secret")]
        protocol._write_outgoing_data.side_effect = AssertionError("Passive observation must not write")
        client = SimpleNamespace(_transport=SimpleNamespace(
            _pool=SimpleNamespace(connections=[SimpleNamespace(_connection=protocol)])))
        with patch("benchmark.diagnostics.tcp_keepalive_capture.select.select", return_value=([sock], [], [])):
            result = passive_read(client, "https://example.test/file?Signature=do-not-save",
                                  "direct.os_enabled", Timeline(), time.monotonic() + 2)
        self.assertEqual(result["events"][0]["error_code"], 0)
        self.assertEqual(result["read_error_type"], "RemoteProtocolError")
        protocol._write_outgoing_data.assert_not_called()
        protocol.handle_request.assert_not_called()
        self.assertNotIn("do-not-save", json.dumps(result))
        self.assertNotIn("secret", json.dumps(result))

    def test_socket_factory_is_restored_after_failed_connect(self):
        original = socket.create_connection
        sock = Mock()
        sock.connect.side_effect = OSError("Failed connect")
        profile = ContextVar("test_capture_profile", default="enabled")
        with self.assertRaises(OSError):
            with reserved_connections("example.test", "192.0.2.1", {"enabled": sock}, profile):
                socket.create_connection(("example.test", 443), timeout=3)
        self.assertIs(socket.create_connection, original)
        sock.connect.assert_called_once_with(("192.0.2.1", 443))

    def test_root_process_without_readable_uid_is_not_selected(self):
        output = Path("/tmp/test-scope.pcapng")
        unreadable = SimpleNamespace(info={"name": "tcpdump", "cmdline": [str(output)], "uids": None})
        wanted = SimpleNamespace(info={"name": "tcpdump", "cmdline": [str(output)],
                                       "uids": SimpleNamespace(effective=os.getuid())})
        with patch("benchmark.diagnostics.tcp_keepalive_capture.psutil.process_iter", return_value=[unreadable, wanted]):
            self.assertIs(find_capture_process(output), wanted)

    def test_invalid_capture_scope_is_rejected_before_privileged_execution(self):
        with self.assertRaises((OSError, ValueError)):
            capture_arguments("192.0.2.1; invalid", [10001, 10002], Path("/tmp/test.pcapng"))
        with self.assertRaises(ValueError):
            capture_arguments("192.0.2.1", [10001, "10002"], Path("/tmp/test.pcapng"))
        with self.assertRaises(ValueError):
            capture_arguments("192.0.2.1", [10001, 0], Path("/tmp/test.pcapng"))
