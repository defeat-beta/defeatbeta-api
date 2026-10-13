"""Prevent successful responses from hiding replacement connections."""

from copy import deepcopy
import json
import unittest

import httpx

from benchmark.diagnostics.cdn_active import sample, summarize
from benchmark.diagnostics.connection_timeline import Timeline


class TestCdnActive(unittest.TestCase):
    def test_one_byte_validation_and_no_outer_retry(self):
        requests = []

        def respond(request):
            requests.append(request)
            self.assertEqual(request.headers["Range"], "bytes=0-0")
            if len(requests) == 1:
                raise httpx.ReadError("Signature=do-not-save")
            return httpx.Response(206, content=b"x",
                                  headers={"Content-Range": "bytes 1-1/100"})

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            failed = sample(client, "https://example.test/file", 100, Timeline())
            self.assertEqual(len(requests), 1)
            invalid = sample(client, "https://example.test/file", 100, Timeline())
        self.assertFalse(failed["success"])
        self.assertFalse(invalid["success"])
        self.assertNotIn("do-not-save", json.dumps(failed))
        self.assertNotIn("sha256", invalid)

    def test_same_connection_requires_identity_streams_and_handshake_evidence(self):
        samples = [{"success": True, "connection_id": 1, "local_port": 10001,
                    "socket_peer_host": "192.0.2.1", "socket_peer_port": 443,
                    "http_version": "HTTP/2", "stream_id": stream,
                    "sha256": "fingerprint", "completed_elapsed_seconds": index * 10,
                    "protocol_attempts": [{"connection_id": 1}]}
                   for index, stream in enumerate((1, 3, 5))]
        events = [{"phase": phase, "outcome": "complete"}
                  for phase in ("connection.connect_tcp", "connection.start_tls")]
        self.assertTrue(summarize(samples, events)["same_connection_throughout"])
        replacement = deepcopy(samples)
        replacement[-1].update(connection_id=2, local_port=10002, stream_id=1)
        replacement[-1]["protocol_attempts"].append({"connection_id": 2})
        self.assertFalse(summarize(replacement, events)["same_connection_throughout"])
        missing = deepcopy(samples)
        missing[-1]["local_port"] = None
        self.assertFalse(summarize(missing, events)["same_connection_throughout"])
        self.assertFalse(summarize(samples, events + [{"phase": "http2.goaway_received"}])[
            "same_connection_throughout"])
        self.assertFalse(summarize(samples, events + events)["same_connection_throughout"])
