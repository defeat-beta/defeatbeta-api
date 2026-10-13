"""Validate diagnostic attribution without changing the product pipeline."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import Future
import json
import ssl
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import httpx

from benchmark.diagnostics.cache_timeline import CacheTimeline
from defeatbeta_api.client.dataset_cache_fs import DatasetCacheFileSystem
from defeatbeta_api.client.http_pool import ConnectionManager, ManagedHTTPTransport
from defeatbeta_api.client.http_runtime import HTTPRuntime, ResponseStream
from test.http2_peer import http2_peer
from test.test_dataset_cache_fs import FakeRangeClient, PINNED


class TestCacheTimeline(unittest.TestCase):
    def test_async_http2_read_lock_wait_is_not_a_socket_read(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        import httpcore
        from httpcore._async.http2 import AsyncHTTP2Connection

        timeline = CacheTimeline()

        async def contend():
            connection = AsyncHTTP2Connection(httpcore.Origin(b"https", b"example.test", 443),
                                              SimpleNamespace(write=AsyncMock()))
            connection._events[1] = [object()]
            with timeline.request("test", "GET", "https://example.test/data"):
                async with connection._read_lock:
                    waiting = asyncio.create_task(connection._receive_events(
                        httpcore.Request("GET", "https://example.test/data"), 1))
                    await asyncio.sleep(0.04)
                await waiting

        with timeline.installed():
            asyncio.run(contend())
        waits = timeline.events_for("transport.async_h2_read_lock_wait")
        self.assertTrue(waits)
        self.assertGreater(max(e["duration_ns"] for e in waits), 30_000_000)
        self.assertEqual(timeline.events_for("transport.socket_read"), [])

    def test_cancellation_before_loop_dispatch_closes_original_coroutine(self):
        runtime = HTTPRuntime()
        entered = threading.Event()
        release = threading.Event()
        operation = asyncio.sleep(0)

        def block_loop():
            entered.set()
            release.wait(timeout=3)

        try:
            runtime._loop.call_soon_threadsafe(block_loop)
            self.assertTrue(entered.wait(timeout=3))
            with CacheTimeline().installed():
                with patch.object(Future, "result", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
                    runtime.call(operation)
                release.set()
                runtime.call(asyncio.sleep(0.02))
            self.assertIsNone(operation.cr_frame)
        finally:
            release.set()
            runtime.close()
            operation.close()

    def test_loop_queue_delay_is_separate_from_awaited_operation(self):
        runtime = HTTPRuntime()
        timeline = CacheTimeline()
        entered = threading.Event()
        release = threading.Event()

        def block_loop():
            entered.set()
            release.wait(timeout=3)

        try:
            runtime._loop.call_soon_threadsafe(block_loop)
            self.assertTrue(entered.wait(timeout=3))
            with timeline.installed(), ThreadPoolExecutor(max_workers=1) as workers:
                result = workers.submit(runtime.call, asyncio.sleep(0, result=42))
                try:
                    deadline = time.monotonic() + 3
                    while not timeline.bridges:
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(0.001)
                    time.sleep(0.04)
                finally:
                    release.set()
                self.assertEqual(result.result(timeout=3), 42)
            item = timeline.bridges[0]
            self.assertGreater(item["submit_to_start_ns"], 30_000_000)
            self.assertGreater(item["submit_to_start_ns"], item["operation_ns"])
        finally:
            release.set()
            runtime.close()

    def test_concurrent_downloads_keep_task_ids_through_requests_and_writes(self):
        payload = bytes(range(256)) * 1024
        timeline = CacheTimeline()
        with http2_peer(payload=payload) as (url, certificate, peer), tempfile.TemporaryDirectory() as directory:
            transport = ManagedHTTPTransport(http2=True, manager=ConnectionManager(),
                                            verify=ssl.create_default_context(cafile=certificate))
            with httpx.Client(transport=transport, trust_env=False) as client:
                fs = DatasetCacheFileSystem(directory, "diagnostic-v1",
                    lambda original, refresh=False: (url, len(payload)), http_client=client, workers=4)
                try:
                    path = fs.register(PINNED)
                    with timeline.installed(filesystems=[fs]), ThreadPoolExecutor(max_workers=4) as workers:
                        values = list(workers.map(lambda i: fs.cat_file(path, i * 65536, (i + 1) * 65536), range(4)))
                        self.assertEqual(b"".join(values), payload)
                        self.assertEqual(fs.await_pending()["errors"], 0)
                    task_ids = {item["id"] for item in timeline.tasks}
                    self.assertEqual(len(task_ids), 4)
                    self.assertEqual({item["task_id"] for item in timeline.requests}, task_ids)
                    for phase in ("cache.worker_queue", "cache.fetch_block", "cache.atomic_write",
                                  "cache.generation_lock_wait", "cache.prune"):
                        self.assertEqual({e["task_id"] for e in timeline.events_for(phase)}, task_ids)
                    self.assertTrue(all(item["task_id"] in task_ids for item in timeline.bridges))
                finally:
                    fs.close()

    def test_generation_wait_is_not_reported_as_network_or_publish_wait(self):
        with tempfile.TemporaryDirectory() as directory:
            fs = DatasetCacheFileSystem(directory, "diagnostic-v1", lambda url, refresh=False: url,
                                        http_client=FakeRangeClient(1024))
            path = fs.register(PINNED)
            key, url = fs._key_and_url(path)
            timeline = CacheTimeline()
            original = fs._generation_lock
            try:
                with timeline.installed(filesystems=[fs]), ThreadPoolExecutor(max_workers=1) as executor:
                    with fs._generation_lock:
                        future = executor.submit(fs._fetch_block, key, url, 0, 128, 1024)
                        deadline = time.monotonic() + 3
                        while not timeline.events_for("cache.request_range"):
                            self.assertLess(time.monotonic(), deadline)
                            time.sleep(0.001)
                        time.sleep(0.04)
                    self.assertEqual(len(future.result(timeout=3)), 128)
                waits = timeline.events_for("cache.generation_lock_wait", task_only=True)
                self.assertGreater(max(e["duration_ns"] for e in waits), 30_000_000)
                self.assertEqual(len(timeline.tasks), 1)
                self.assertGreater(timeline.tasks[0]["duration_ns"], 30_000_000)
                self.assertTrue(timeline.events_for("cache.atomic_write", task_only=True))
                self.assertTrue(timeline.events_for("cache.checksum", task_only=True))
                self.assertIs(fs._generation_lock, original)
            finally:
                fs.close()

    def test_bridge_records_operation_separately_and_preserves_payload(self):
        runtime = HTTPRuntime()
        timeline = CacheTimeline()

        class Stream:
            async def __aiter__(self):
                await asyncio.sleep(0.04)
                yield b"first"
                yield b"second"

            async def aclose(self):
                pass

        try:
            with timeline.installed():
                stream = ResponseStream(Stream(), runtime)
                self.assertEqual(b"".join(stream), b"firstsecond")
                stream.close()
            calls = timeline.bridges
            self.assertEqual(len(calls), 4)
            self.assertGreater(calls[0]["operation_ns"], 30_000_000)
            for item in calls:
                self.assertEqual(item["duration_ns"], item["submit_to_start_ns"]
                                 + item["operation_ns"] + item["complete_to_return_ns"])
                self.assertGreaterEqual(item["submit_to_start_ns"], 0)
                self.assertGreaterEqual(item["complete_to_return_ns"], 0)
            self.assertEqual(calls[-2]["error_type"], "StopAsyncIteration")
        finally:
            runtime.close()

    def test_closed_runtime_does_not_leak_wrapped_coroutine(self):
        runtime = HTTPRuntime()
        runtime.close()
        operation = asyncio.sleep(0)
        with CacheTimeline().installed(), self.assertRaises(RuntimeError):
            runtime.call(operation)
        self.assertIsNone(operation.cr_frame)

    def test_http2_header_and_body_delays_have_distinct_spans(self):
        payload = b"abcd" * 32768
        timeline = CacheTimeline()
        with http2_peer(payload=payload, response_delay=0.04, body_delay=0.03,
                       body_chunk_size=16384) as (url, certificate, peer):
            transport = ManagedHTTPTransport(http2=True, manager=ConnectionManager(),
                                            verify=ssl.create_default_context(cafile=certificate))
            with httpx.Client(transport=transport, trust_env=False) as client, timeline.installed():
                response = client.get(url + "?Signature=secret", headers={"Range": "bytes=0-131071"})
                self.assertEqual(response.content, payload)
                self.assertEqual(response.http_version, "HTTP/2")
        request = timeline.requests[0]
        self.assertGreater(request["headers_received_ns"] - request["start_ns"], 30_000_000)
        self.assertGreater(request["last_body_delivered_ns"] - request["headers_received_ns"], 150_000_000)
        self.assertEqual(request["body_bytes"], len(payload))
        artifact = timeline.artifact()
        self.assertIn("events", artifact)
        self.assertIn("bridges", artifact)
        self.assertNotIn("secret", json.dumps(artifact))

    def test_failed_worker_is_recorded_and_hooks_are_restored(self):
        timeline = CacheTimeline()
        original = HTTPRuntime.call

        def _fetch_block():
            raise ValueError("Signature=secret")

        with timeline.installed(), ThreadPoolExecutor(max_workers=1) as executor:
            with self.assertRaises(ValueError):
                executor.submit(_fetch_block).result(timeout=3)
        self.assertEqual(timeline.tasks[0]["error_type"], "ValueError")
        self.assertIs(HTTPRuntime.call, original)
        self.assertNotIn("secret", json.dumps(timeline.artifact()))

    def test_short_local_run_preserves_raw_records_and_rejects_overwrite(self):
        from pathlib import Path
        from types import SimpleNamespace
        from benchmark.diagnostics.cache_pipeline import run

        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(output=Path(directory) / "report.json", workers=[2],
                                   tasks=4, range_bytes=32768, rounds=1)
            report = run(args)
            self.assertEqual(report["status"], "complete")
            self.assertEqual(len(report["cases"]), 2)
            plain, detailed = report["cases"]
            self.assertEqual(plain["downloaded_bytes"], detailed["downloaded_bytes"])
            self.assertEqual(len(detailed["pipeline"]["tasks"]), 4)
            self.assertTrue(detailed["pipeline"]["events"])
            self.assertEqual(json.loads(args.output.read_text())["status"], "complete")
            with self.assertRaises(FileExistsError):
                run(args)


if __name__ == "__main__":
    unittest.main()
