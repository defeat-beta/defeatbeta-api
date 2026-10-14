"""Verify the synchronous facade around the existing async HTTP stack."""

import asyncio
from concurrent.futures import CancelledError
from concurrent.futures import ThreadPoolExecutor
from threading import get_ident
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpcore

from defeatbeta_api.client.http_runtime import Connection, HTTPRuntime, ResponseStream


class TestHTTPRuntime(unittest.TestCase):
    def setUp(self):
        self.runtime = HTTPRuntime()

    def tearDown(self):
        self.runtime.close()

    def test_concurrent_callers_share_one_protocol_thread(self):
        async def operation():
            before = get_ident()
            await asyncio.sleep(0.005)
            return before, get_ident()

        with ThreadPoolExecutor(max_workers=16) as executor:
            results = list(executor.map(lambda _: self.runtime.call(operation()), range(64)))
        self.assertEqual(len(set(results)), 1)
        self.assertNotEqual(results[0][0], get_ident())

    def test_failure_does_not_poison_later_operations(self):
        async def fail():
            raise ValueError("Expected failure")

        with self.assertRaisesRegex(ValueError, "Expected failure"):
            self.runtime.call(fail())
        self.assertEqual(self.runtime.call(asyncio.sleep(0, result=42)), 42)

    def test_response_bytes_and_close_use_the_protocol_thread(self):
        threads = []

        class Stream:
            async def __aiter__(self):
                threads.append(get_ident())
                yield b"first"
                await asyncio.sleep(0)
                yield b"second"

            async def aclose(self):
                threads.append(get_ident())

        response = ResponseStream(Stream(), self.runtime)
        self.assertEqual(list(response), [b"first", b"second"])
        response.close()
        self.assertEqual(len(set(threads)), 1)
        self.assertNotEqual(threads[0], get_ident())

    def test_buffered_response_scheduling_does_not_grow_with_fragment_count(self):
        for fragments in (0, 1, 128):
            with self.subTest(fragments=fragments):
                threads, closed = [], []

                class Stream:
                    async def __aiter__(self):
                        for _ in range(fragments):
                            threads.append(get_ident())
                            yield b"payload"

                    async def aclose(self):
                        closed.append(get_ident())

                async def request(request):
                    threads.append(get_ident())
                    return httpcore.Response(200, content=Stream())

                with patch("defeatbeta_api.client.http_runtime.runtime", return_value=self.runtime):
                    connection = Connection(SimpleNamespace(handle_async_request=request))
                with patch.object(self.runtime, "call", wraps=self.runtime.call) as calls:
                    response = connection.handle_request(httpcore.Request(
                        "GET", "https://cdn.test/file", extensions={"defeatbeta_buffer_response": True}))
                    self.assertEqual(response.read(), b"payload" * fragments)
                    response.close()
                self.assertEqual(closed, [self.runtime._thread.ident])
                self.assertEqual(set(threads), {self.runtime._thread.ident})
                self.assertEqual(calls.call_count, 1)

    def test_buffered_read_failure_closes_response_on_protocol_thread(self):
        for error, expected in ((httpcore.ReadTimeout("Read timed out"), httpcore.ReadTimeout),
                                (httpcore.ReadError("Peer disconnected"), httpcore.ReadError),
                                (asyncio.CancelledError(), CancelledError)):
            with self.subTest(error=type(error).__name__):
                closed = []

                class Stream:
                    async def __aiter__(self):
                        yield b"partial"
                        raise error

                    async def aclose(self):
                        closed.append(get_ident())

                async def request(request):
                    return httpcore.Response(200, content=Stream())

                with patch("defeatbeta_api.client.http_runtime.runtime", return_value=self.runtime):
                    connection = Connection(SimpleNamespace(handle_async_request=request))
                with self.assertRaises(expected):
                    connection.handle_request(httpcore.Request(
                        "GET", "https://cdn.test/file", extensions={"defeatbeta_buffer_response": True}))
                self.assertEqual(closed, [self.runtime._thread.ident])
                self.assertEqual(self.runtime.call(asyncio.sleep(0, result=42)), 42)

    def test_unbuffered_response_is_lazy_and_can_close_before_reading_all_bytes(self):
        consumed, closed = [], []

        class Stream:
            async def __aiter__(self):
                for index in range(128):
                    consumed.append(index)
                    yield b"payload"

            async def aclose(self):
                closed.append(get_ident())

        async def request(request):
            return httpcore.Response(200, content=Stream())

        with patch("defeatbeta_api.client.http_runtime.runtime", return_value=self.runtime):
            connection = Connection(SimpleNamespace(handle_async_request=request))
        response = connection.handle_request(httpcore.Request("GET", "https://cdn.test/file"))
        self.assertEqual(consumed, [])
        iterator = response.iter_stream()
        self.assertEqual(next(iterator), b"payload")
        response.close()
        self.assertEqual(consumed, [0])
        self.assertEqual(closed, [self.runtime._thread.ident])

    def test_closed_runtime_rejects_work_without_leaking_coroutines(self):
        self.runtime.close()
        operation = asyncio.sleep(0)
        with self.assertRaisesRegex(RuntimeError, "closed"):
            self.runtime.call(operation)
        self.assertIsNone(operation.cr_frame)

    def test_socket_option_failure_closes_async_stream_and_preserves_error(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        import httpcore
        from defeatbeta_api.client.http_pool import ConnectionManager, _RoutePool
        from defeatbeta_api.client.http_runtime import Connection

        closed = []

        def setsockopt(*args):
            raise OSError("Socket option failed")

        async def close_stream():
            closed.append(get_ident())

        stream = SimpleNamespace(get_extra_info=lambda key: SimpleNamespace(setsockopt=setsockopt),
                                 aclose=close_stream)

        async def request(request):
            await request.extensions["trace"]("connection.connect_tcp.complete", {"return_value": stream})

        async def close_connection():
            pass

        raw = SimpleNamespace(handle_async_request=request, aclose=close_connection)
        with patch("defeatbeta_api.client.http_runtime.runtime", return_value=self.runtime):
            route = _RoutePool(SimpleNamespace(create_connection=lambda origin: Connection(raw), close=lambda: None),
                               ConnectionManager(), socket_options=[(1, 2, 3)])
            try:
                with self.assertRaisesRegex(OSError, "Socket option failed"):
                    route.handle_request(httpcore.Request("GET", "https://cdn.test/file"))
                self.assertEqual(closed, [self.runtime._thread.ident])
            finally:
                route.close()


if __name__ == "__main__":
    unittest.main()
