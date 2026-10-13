"""Exercise receive coordination with valid HTTP/2 frames and gated input."""

import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import h2.config
import h2.connection
import h2.events
import h2.exceptions
import h2.settings
import httpcore
from httpcore._async.http2 import AsyncHTTP2Connection, HTTPConnectionState

from defeatbeta_api.client.http_pool import ConnectionManager


class InputStream:
    def __init__(self, peer):
        self.peer = peer
        self.input = asyncio.Queue()
        self.read_started = asyncio.Queue()
        self.reads = 0
        self.active_reads = 0
        self.max_active_reads = 0
        self.timeouts = []

    async def read(self, max_bytes, timeout=None):
        self.reads += 1
        self.active_reads += 1
        self.max_active_reads = max(self.max_active_reads, self.active_reads)
        self.timeouts.append(timeout)
        self.read_started.put_nowait(self.reads)
        try:
            item = await self.input.get()
            if isinstance(item, Exception):
                raise item
            return item
        finally:
            self.active_reads -= 1

    async def write(self, data, timeout=None):
        if data:
            self.peer.receive_data(data)

    async def aclose(self):
        self.input.put_nowait(b"")


class TestHTTP2Receive(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tasks = []
        self.manager = ConnectionManager()
        self.peer = h2.connection.H2Connection(config=h2.config.H2Configuration(client_side=False))
        self.connection = AsyncHTTP2Connection(httpcore.Origin(b"https", b"example.test", 443), None)
        protocol = self.connection._h2_state
        protocol.initiate_connection()
        self.peer.initiate_connection()
        self.peer.receive_data(protocol.data_to_send())
        protocol.receive_data(self.peer.data_to_send())
        self.peer.receive_data(protocol.data_to_send())
        for stream_id in (1, 3, 5):
            protocol.send_headers(stream_id, [(":method", "GET"), (":scheme", "https"),
                (":authority", "example.test"), (":path", f"/{stream_id}")], end_stream=True)
            self.connection._events[stream_id] = []
        self.peer.receive_data(protocol.data_to_send())
        for stream_id in (1, 3, 5):
            self.peer.send_headers(stream_id, [(":status", "200")])
        protocol.receive_data(self.peer.data_to_send())
        self.stream = InputStream(self.peer)
        self.connection._network_stream = self.stream
        self.connection._state = HTTPConnectionState.ACTIVE
        self.connection._request_count = 3
        self.connection._max_streams = 3
        self.manager.observe(SimpleNamespace(raw=self.connection), "http2.send_request_headers.started")

    async def asyncTearDown(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.connection.aclose()

    async def start(self, stream_id):
        request = httpcore.Request("GET", f"https://example.test/{stream_id}",
                                   extensions={"timeout": {"read": 7}})
        task = asyncio.create_task(self.connection._receive_stream_event(request, stream_id))
        self.tasks.append(task)
        # The existing reader is already parked before followers are started.
        await asyncio.sleep(0)
        return task

    def feed(self):
        self.stream.input.put_nowait(self.peer.data_to_send())

    async def test_ready_data_does_not_wait_for_later_network_input(self):
        first = await self.start(1)
        await asyncio.wait_for(self.stream.read_started.get(), 1)
        later = await self.start(3)
        ready = await self.start(5)
        self.peer.send_data(5, b"ready", end_stream=True)
        self.peer.send_data(1, b"reader", end_stream=True)
        self.feed()
        self.assertEqual((await asyncio.wait_for(first, 1)).data, b"reader")
        await asyncio.wait_for(self.stream.read_started.get(), 1)
        self.assertEqual((await asyncio.wait_for(asyncio.shield(ready), 0.2)).data, b"ready")
        self.assertFalse(later.done())
        self.assertEqual(self.stream.reads, 2)
        self.assertEqual(self.stream.max_active_reads, 1)
        self.peer.send_data(3, b"later", end_stream=True)
        self.feed()
        self.assertEqual((await asyncio.wait_for(later, 1)).data, b"later")

    async def test_reverse_waiter_order_also_consumes_ready_data(self):
        first = await self.start(1)
        await asyncio.wait_for(self.stream.read_started.get(), 1)
        ready = await self.start(5)
        later = await self.start(3)
        self.peer.send_data(5, b"ready", end_stream=True)
        self.peer.send_data(1, b"reader", end_stream=True)
        self.feed()
        self.assertEqual((await asyncio.wait_for(ready, 1)).data, b"ready")
        self.assertEqual((await asyncio.wait_for(first, 1)).data, b"reader")
        self.assertFalse(later.done())

    async def test_cancelled_waiter_does_not_cancel_the_reader(self):
        first = await self.start(1)
        await asyncio.wait_for(self.stream.read_started.get(), 1)
        cancelled = await self.start(3)
        ready = await self.start(5)
        cancelled.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await cancelled
        self.assertEqual(self.stream.active_reads, 1)
        self.peer.send_data(1, b"reader", end_stream=True)
        self.peer.send_data(5, b"ready", end_stream=True)
        self.feed()
        results = await asyncio.wait_for(asyncio.gather(first, ready), 1)
        self.assertEqual([event.data for event in results], [b"reader", b"ready"])
        self.assertEqual(self.stream.reads, 1)

    async def test_cancelled_reader_hands_off_to_a_waiter(self):
        cancelled = await self.start(1)
        await asyncio.wait_for(self.stream.read_started.get(), 1)
        ready = await self.start(3)
        cancelled.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await cancelled
        await asyncio.wait_for(self.stream.read_started.get(), 1)
        self.peer.send_data(3, b"ready", end_stream=True)
        self.feed()
        self.assertEqual((await asyncio.wait_for(ready, 1)).data, b"ready")
        self.assertEqual(self.stream.max_active_reads, 1)

    async def test_response_close_wakes_its_waiter_without_interrupting_reader(self):
        first = await self.start(1)
        await asyncio.wait_for(self.stream.read_started.get(), 1)
        closed = await self.start(3)
        await self.connection._response_closed(3)
        with self.assertRaisesRegex(httpcore.ReadError, "response stream is closed"):
            await asyncio.wait_for(closed, 1)
        self.assertFalse(first.done())
        self.assertEqual(self.stream.active_reads, 1)

    async def test_connection_close_wakes_every_waiter(self):
        first = await self.start(1)
        await asyncio.wait_for(self.stream.read_started.get(), 1)
        others = [await self.start(i) for i in (3, 5)]
        await self.connection.aclose()
        results = await asyncio.wait_for(asyncio.gather(first, *others, return_exceptions=True), 1)
        self.assertTrue(all(isinstance(result, (httpcore.ReadError, httpcore.RemoteProtocolError))
                            for result in results), results)
        self.assertEqual(self.stream.reads, 1)
        self.assertEqual(self.stream.active_reads, 0)

    async def test_read_timeout_is_shared_without_repeating_socket_reads(self):
        first = await self.start(1)
        await asyncio.wait_for(self.stream.read_started.get(), 1)
        others = [await self.start(i) for i in (3, 5)]
        error = httpcore.ReadTimeout("Controlled read timeout")
        self.stream.input.put_nowait(error)
        results = await asyncio.wait_for(asyncio.gather(first, *others, return_exceptions=True), 1)
        self.assertTrue(all(result is error for result in results))
        self.assertEqual(self.stream.timeouts, [7])
        self.assertFalse(self.connection.is_available())

    async def test_goaway_retains_per_stream_retry_classification(self):
        first = await self.start(1)
        await asyncio.wait_for(self.stream.read_started.get(), 1)
        others = [await self.start(i) for i in (3, 5)]
        self.peer.close_connection(last_stream_id=1)
        self.feed()
        results = await asyncio.wait_for(asyncio.gather(first, *others, return_exceptions=True), 1)
        self.assertIsInstance(results[0], httpcore.RemoteProtocolError)
        self.assertTrue(all(isinstance(result, httpcore.ConnectionNotAvailable) for result in results[1:]))
        self.assertEqual(self.connection._request_count, 1)
        self.assertEqual(self.stream.reads, 1)

    async def test_reset_affects_only_its_stream(self):
        first = await self.start(1)
        await asyncio.wait_for(self.stream.read_started.get(), 1)
        reset = await self.start(3)
        ready = await self.start(5)
        self.peer.reset_stream(3)
        self.peer.send_data(1, b"reader", end_stream=True)
        self.peer.send_data(5, b"ready", end_stream=True)
        self.feed()
        results = await asyncio.wait_for(asyncio.gather(first, reset, ready, return_exceptions=True), 1)
        self.assertEqual(results[0].data, b"reader")
        self.assertIsInstance(results[1], httpcore.RemoteProtocolError)
        self.assertEqual(results[2].data, b"ready")
        self.assertTrue(self.connection.is_available())

    async def test_settings_reduction_does_not_block_dispatch(self):
        first = await self.start(1)
        await asyncio.wait_for(self.stream.read_started.get(), 1)
        ready = await self.start(3)
        self.peer.update_settings({h2.settings.SettingCodes.MAX_CONCURRENT_STREAMS: 1})
        self.peer.send_data(3, b"ready", end_stream=True)
        self.peer.send_data(1, b"reader", end_stream=True)
        self.feed()
        results = await asyncio.wait_for(asyncio.gather(first, ready), 1)
        self.assertEqual([event.data for event in results], [b"reader", b"ready"])
        self.assertEqual(self.connection._max_streams, 1)

    async def test_flow_waiter_rechecks_window_before_another_read_finishes(self):
        protocol = self.connection._h2_state
        protocol.send_headers(7, [(":method", "POST"), (":scheme", "https"),
            (":authority", "example.test"), (":path", "/upload")])
        self.peer.receive_data(protocol.data_to_send())
        self.connection._events[7] = []
        self.peer.update_settings({h2.settings.SettingCodes.INITIAL_WINDOW_SIZE: 0})
        self.feed()
        request = httpcore.Request("POST", "https://example.test/upload")
        await self.connection._receive_events(request)
        await self.stream.read_started.get()
        self.assertEqual(protocol.local_flow_control_window(7), 0)
        first = await self.start(1)
        await asyncio.wait_for(self.stream.read_started.get(), 1)
        later = await self.start(3)
        flow = asyncio.create_task(self.connection._wait_for_outgoing_flow(request, 7))
        self.tasks.append(flow)
        await asyncio.sleep(0)
        self.peer.increment_flow_control_window(123, stream_id=7)
        self.peer.send_data(1, b"reader", end_stream=True)
        self.feed()
        self.assertEqual((await asyncio.wait_for(first, 1)).data, b"reader")
        self.assertEqual(await asyncio.wait_for(flow, 1), 123)
        self.assertFalse(later.done())
        self.assertEqual(self.stream.max_active_reads, 1)

    async def test_ordered_buffered_data_does_not_trigger_prefetch(self):
        first = await self.start(1)
        await asyncio.wait_for(self.stream.read_started.get(), 1)
        for data in (b"a", b"b", b"c"):
            self.peer.send_data(1, data, end_stream=data == b"c")
        self.feed()
        self.assertEqual((await asyncio.wait_for(first, 1)).data, b"a")
        request = httpcore.Request("GET", "https://example.test/1")
        events = [await self.connection._receive_stream_event(request, 1) for _ in range(3)]
        self.assertEqual([event.data for event in events[:2]], [b"b", b"c"])
        self.assertIsInstance(events[-1], h2.events.StreamEnded)
        self.assertEqual(self.stream.reads, 1)

    async def test_write_failure_is_shared_even_after_data_is_queued(self):
        first = await self.start(1)
        await asyncio.wait_for(self.stream.read_started.get(), 1)
        ready = await self.start(3)
        error = httpcore.WriteTimeout("Controlled write timeout")

        async def fail_write(data, timeout=None):
            raise error

        self.stream.write = fail_write
        self.peer.send_data(1, b"reader", end_stream=True)
        self.peer.send_data(3, b"ready", end_stream=True)
        self.feed()
        results = await asyncio.wait_for(asyncio.gather(first, ready, return_exceptions=True), 1)
        self.assertTrue(all(result is error for result in results), results)
        self.assertFalse(self.connection.is_available())

    async def test_eof_fails_waiters_without_an_extra_read(self):
        first = await self.start(1)
        await asyncio.wait_for(self.stream.read_started.get(), 1)
        ready = await self.start(3)
        self.stream.input.put_nowait(b"")
        results = await asyncio.wait_for(asyncio.gather(first, ready, return_exceptions=True), 1)
        self.assertTrue(all(isinstance(result, httpcore.RemoteProtocolError) for result in results), results)
        self.assertEqual(self.stream.reads, 1)
        self.assertEqual(self.stream.active_reads, 0)

    async def test_invalid_connection_frame_fails_all_waiters(self):
        first = await self.start(1)
        await asyncio.wait_for(self.stream.read_started.get(), 1)
        others = [await self.start(i) for i in (3, 5)]
        # DATA is forbidden on stream zero. This is a connection-level error.
        self.stream.input.put_nowait(b"\x00\x00\x01\x00\x00\x00\x00\x00\x00x")
        results = await asyncio.wait_for(asyncio.gather(first, *others, return_exceptions=True), 0.2)
        self.assertTrue(all(isinstance(result, h2.exceptions.ProtocolError) for result in results), results)
        self.assertEqual(self.stream.reads, 1)

    async def test_installation_is_per_connection_and_idempotent(self):
        installed = self.connection._receive_events
        self.manager.observe(SimpleNamespace(raw=self.connection), "http2.send_request_headers.started")
        self.assertIs(self.connection._receive_events, installed)
        unrelated = AsyncHTTP2Connection(httpcore.Origin(b"https", b"example.test", 443), None)
        self.assertIs(unrelated._receive_events.__func__, AsyncHTTP2Connection._receive_events)

    async def test_adapter_does_not_retain_a_finished_diagnostic_scope(self):
        calls = []
        candidate = AsyncHTTP2Connection(httpcore.Origin(b"https", b"example.test", 443), None)

        async def first_scope(connection, request, stream_id=None):
            calls.append("first")

        async def second_scope(connection, request, stream_id=None):
            calls.append("second")

        request = httpcore.Request("GET", "https://example.test/")
        with patch.object(AsyncHTTP2Connection, "_receive_events", first_scope):
            self.manager.observe(SimpleNamespace(raw=candidate), "http2.send_request_headers.started")
            await candidate._receive_events(request)
        with patch.object(AsyncHTTP2Connection, "_receive_events", second_scope):
            await candidate._receive_events(request)
        self.assertEqual(calls, ["first", "second"])

    async def test_repeated_handoffs_preserve_every_stream_event(self):
        rounds = 50
        stream_ids = tuple(range(1, 128, 2))
        protocol = self.connection._h2_state
        for stream_id in stream_ids[3:]:
            protocol.send_headers(stream_id, [(":method", "GET"), (":scheme", "https"),
                (":authority", "example.test"), (":path", f"/{stream_id}")], end_stream=True)
            self.connection._events[stream_id] = []
        self.peer.receive_data(protocol.data_to_send())
        for stream_id in stream_ids[3:]:
            self.peer.send_headers(stream_id, [(":status", "200")])
        protocol.receive_data(self.peer.data_to_send())

        async def consume(stream_id):
            request = httpcore.Request("GET", f"https://example.test/{stream_id}")
            values = []
            for _ in range(rounds):
                event = await self.connection._receive_stream_event(request, stream_id)
                values.append(event.data)
            return values

        consumers = [asyncio.create_task(consume(i)) for i in stream_ids]
        self.tasks.extend(consumers)
        for number in range(rounds):
            await asyncio.wait_for(self.stream.read_started.get(), 1)
            for stream_id in reversed(stream_ids):
                self.peer.send_data(stream_id, str(number).encode(), end_stream=number == rounds - 1)
            self.feed()
        results = await asyncio.wait_for(asyncio.gather(*consumers), 1)
        expected = [str(i).encode() for i in range(rounds)]
        self.assertEqual(results, [expected] * len(stream_ids))
        self.assertEqual(self.stream.reads, rounds)
        self.assertEqual(self.stream.max_active_reads, 1)


if __name__ == "__main__":
    unittest.main()
