"""Check that diagnostic hooks preserve payloads and observe real connections."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
import unittest
import ssl

import httpx

from benchmark.diagnostics.connection_timeline import Timeline
from test.http2_peer import http2_peer


@contextmanager
def server(*, close=False, coalesce=False):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            time.sleep(0.03)
            self.send_response(200)
            self.send_header("Content-Length", "6")
            if close:
                self.send_header("Connection", "close")
            self.end_headers()
            if coalesce:
                self.wfile.write(b"abcdef")
                self.wfile.flush()
                return
            self.wfile.write(b"abc")
            self.wfile.flush()
            time.sleep(0.03)
            self.wfile.write(b"def")
            self.wfile.flush()

        def log_message(self, *args):
            pass

    local = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    local.daemon_threads = True
    thread = threading.Thread(target=local.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{local.server_port}"
    finally:
        local.shutdown()
        local.server_close()
        thread.join(timeout=2)


class TestConnectionTimeline(unittest.TestCase):
    def test_managed_async_protocol_reports_connections_and_socket_waits(self):
        from defeatbeta_api.client.http_pool import ConnectionManager, ManagedHTTPTransport

        timeline = Timeline()
        manager = ConnectionManager()
        with http2_peer(response_delay=0.03) as (url, certificate, peer):
            transport = ManagedHTTPTransport(
                http2=True, verify=ssl.create_default_context(cafile=certificate), manager=manager)
            with timeline.installed(), httpx.Client(transport=transport, trust_env=False) as client:
                self.assertEqual(client.get(url + "/price").content, b"x")
                self.assertEqual(client.get(url + "/profile").content, b"x")
        first, second = timeline.requests
        self.assertIsNotNone(first.get("connection_id"))
        self.assertEqual(first["connection_id"], second["connection_id"])
        phases = {event["phase"] for event in timeline.events}
        self.assertIn("transport.socket_read", phases)
        self.assertIn("transport.protocol_until_headers", phases)
        self.assertIn("transport.connection_close", phases)

    def test_stream_queue_is_measured_separately_from_connection_pool(self):
        timeline = Timeline()
        with http2_peer(max_concurrent_streams=1, response_delay=0.12) as (url, certificate, peer):
            with httpx.Client(http2=True, verify=ssl.create_default_context(cafile=certificate),
                              trust_env=False) as client:
                self.assertEqual(client.get(url).content, b"x")
                with timeline.installed(), ThreadPoolExecutor(max_workers=3) as workers:
                    responses = list(workers.map(lambda _: client.get(url).content, range(3)))
                self.assertEqual(responses, [b"x"] * 3)
                self.assertEqual(peer.connections, 1)
        waits = [event for event in timeline.events if event["phase"] == "transport.h2_stream_wait"]
        self.assertEqual(len(waits), 3)
        self.assertTrue(all(event["effective_stream_limit"] == 1 for event in waits))
        self.assertEqual(len({event["request_id"] for event in waits}), 3)
        self.assertGreater(sum(event["duration_ns"] for event in waits), 200_000_000)
        pool_wait = sum(event["duration_ns"] for event in timeline.events
                        if event["phase"] == "transport.pool_wait")
        self.assertLess(pool_wait, 50_000_000)

    def test_query_summary_merges_parallel_http_spans(self):
        timeline = Timeline()
        query = {"id": 1, "start_ns": 0, "end_ns": 100, "duration_ns": 100}
        timeline.requests = [
            {"query_id": 1, "start_ns": 10, "end_ns": 50},
            {"query_id": 1, "start_ns": 30, "end_ns": 70},
            {"query_id": 2, "start_ns": 0, "end_ns": 100},
        ]
        summary = timeline.query_summary(query)
        self.assertEqual(summary["http_requests"], 2)
        self.assertAlmostEqual(summary["observed_http_wall_seconds"], 60 / 1e9)
        self.assertAlmostEqual(summary["outside_observed_http_seconds"], 40 / 1e9)

    def test_prefetch_worker_retains_its_query_identity(self):
        timeline = Timeline()
        with server() as url, httpx.Client(trust_env=False) as client, timeline.installed():
            def _fetch_block():
                return client.get(url).content

            with ThreadPoolExecutor(max_workers=1) as workers, timeline.query(api="price") as query:
                self.assertEqual(workers.submit(_fetch_block).result(timeout=3), b"abcdef")
        self.assertEqual(timeline.requests[0]["query_id"], query["id"])
        self.assertGreater(timeline.query_summary(query)["observed_http_wall_seconds"], 0.04)
        self.assertIsNone(timeline.query_context.get())

    def test_cross_file_reuse_preserves_body_and_splits_header_wait(self):
        timeline = Timeline()
        with server(coalesce=True) as url, httpx.Client(trust_env=False) as client:
            baseline = client.get(url + "/baseline").content
            with timeline.installed():
                first = client.get(url + "/price?Signature=do-not-save")
                second = client.get(url + "/profile?Token=do-not-save")
                self.assertEqual(first.content, baseline)
                self.assertEqual(second.content, baseline)

        one, two = timeline.requests
        self.assertEqual(one["connection_id"], two["connection_id"])
        self.assertEqual(one["local_port"], two["local_port"])
        self.assertIsNotNone(two["previous_request_end_ns"])
        self.assertEqual(one["body_bytes"], 6)
        self.assertEqual(two["body_bytes"], 6)
        self.assertGreater(one["first_body_delivered_ns"], one["headers_received_ns"])
        # TCP write boundaries do not define application receive boundaries.
        self.assertGreaterEqual(one["last_body_delivered_ns"], one["first_body_delivered_ns"])
        self.assertGreaterEqual(one["body_chunks"], 1)
        waits = [event for event in timeline.events
                 if event["phase"] == "http11.receive_response_headers"]
        self.assertEqual(len(waits), 2)
        self.assertTrue(all(event["duration_ns"] >= 20_000_000 for event in waits))
        self.assertNotIn("do-not-save", json.dumps(timeline.requests + timeline.events))

    def test_body_delivery_timestamps_follow_observed_chunks(self):
        for chunks in ((b"abcdef",), (b"abc", b"def")):
            with self.subTest(chunks=chunks):
                timeline = Timeline()
                now = [0]
                timeline.now = lambda: now[0]

                class BodyStream(httpx.SyncByteStream):
                    def __iter__(self):
                        for chunk in chunks:
                            now[0] += 30_000_000
                            yield chunk

                transport = httpx.MockTransport(
                    lambda request: httpx.Response(200, stream=BodyStream()))
                with timeline.installed(), httpx.Client(transport=transport, trust_env=False) as client:
                    self.assertEqual(client.get("https://example.test/data").content, b"abcdef")
                item, = timeline.requests
                self.assertEqual(item["body_bytes"], 6)
                self.assertEqual(item["body_chunks"], len(chunks))
                self.assertEqual(item["first_body_delivered_ns"], 30_000_000)
                self.assertEqual(item["last_body_delivered_ns"], 30_000_000 * len(chunks))

    def test_server_close_is_observed_as_a_new_connection(self):
        timeline = Timeline()
        with server(close=True) as url, timeline.installed(), httpx.Client(trust_env=False) as client:
            self.assertEqual(client.get(url + "/one").content, b"abcdef")
            self.assertEqual(client.get(url + "/two").content, b"abcdef")
        self.assertNotEqual(timeline.requests[0]["connection_id"],
                            timeline.requests[1]["connection_id"])
        self.assertTrue(any(event["phase"] == "transport.connection_close"
                            for event in timeline.events))

    def test_existing_trace_callback_and_none_are_preserved(self):
        timeline = Timeline()
        seen = []

        def existing(name, info):
            seen.append(name)

        with server() as url, timeline.installed(), httpx.Client(trust_env=False) as client:
            empty = client.build_request("GET", url, extensions={"trace": None})
            self.assertEqual(client.send(empty).content, b"abcdef")
            self.assertIsNone(empty.extensions["trace"])
            request = client.build_request("GET", url, extensions={"trace": existing})
            self.assertEqual(client.send(request).content, b"abcdef")
            self.assertIs(request.extensions["trace"], existing)
        self.assertIn("http11.receive_response_headers.complete", seen)

    def test_failure_is_unchanged_and_hooks_are_restored(self):
        original_send = httpx.Client.send
        original_iterate = httpx.Response.iter_raw
        timeline = Timeline()
        failure = httpx.ReadError("Signature=do-not-save")

        def fail(request):
            raise failure

        request = httpx.Request("GET", "https://example.test/data?Signature=do-not-save")
        with httpx.Client(transport=httpx.MockTransport(fail)) as client:
            with self.assertRaises(httpx.ReadError) as raised:
                with timeline.installed():
                    client.send(request)
            self.assertIs(raised.exception, failure)
        self.assertIs(httpx.Client.send, original_send)
        self.assertIs(httpx.Response.iter_raw, original_iterate)
        self.assertNotIn("trace", request.extensions)
        self.assertEqual(timeline.requests[0]["error_type"], "ReadError")
        self.assertNotIn("do-not-save", json.dumps(timeline.requests + timeline.events))

    def test_worker_requests_have_separate_contexts(self):
        timeline = Timeline()
        with server() as url, timeline.installed(), httpx.Client(trust_env=False) as client:
            with ThreadPoolExecutor(max_workers=3) as workers:
                bodies = list(workers.map(lambda index: client.get(f"{url}/{index}").content,
                                         range(3)))
        self.assertEqual(bodies, [b"abcdef"] * 3)
        self.assertEqual(len({item["id"] for item in timeline.requests}), 3)
        self.assertTrue(all(item["body_bytes"] == 6 for item in timeline.requests))
        self.assertIsNone(timeline.request_context.get())


if __name__ == "__main__":
    unittest.main()
