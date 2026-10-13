"""Reproduce ready-stream blocking independently of diagnostic hooks."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import ssl
import unittest

from benchmark.diagnostics.http2_stream_probe import ready_stream_scenario


class TestHTTP2StreamTimeline(unittest.TestCase):
    def test_ready_blocking_intersects_consumer_wait_and_other_stream_reads(self):
        from benchmark.diagnostics.http2_stream_timeline import StreamTimeline
        timeline = StreamTimeline()
        timeline.stream_events = [{"id": 1, "protocol_connection_id": 1, "stream_id": 5,
            "event_type": "DataReceived", "enqueued_ns": 10, "dequeued_ns": 90,
            "ready_with_waiting_consumer_ns": 80, "dequeue_bridge_id": 1}]

        def span(phase, start, end, connection, stream, bridge=1):
            return {"phase": phase, "start_ns": start, "end_ns": end, "duration_ns": end - start,
                    "protocol_connection_id": connection, "reading_stream_id": stream, "bridge_id": bridge}

        timeline.events = [
            span("transport.async_h2_read_lock_wait", 30, 80, 1, 5),
            span("transport.socket_read", 20, 60, 1, 3),
            span("transport.socket_read", 35, 50, 1, 3),
            span("transport.socket_read", 10, 90, 2, 3),
            span("transport.socket_read", 10, 90, 1, 5),
        ]
        artifact = timeline.artifact()
        self.assertEqual(artifact["stream_events"][0]["ready_blocked_by_other_read_ns"], 30)

    def test_real_tls_body_events_retain_stream_and_bridge_identity(self):
        import httpx
        from benchmark.diagnostics.http2_stream_timeline import StreamTimeline
        from defeatbeta_api.client.http_pool import ConnectionManager, ManagedHTTPTransport
        from test.http2_peer import http2_peer

        payload = bytes(range(256)) * 512
        timeline = StreamTimeline()
        with http2_peer(payload=payload) as (url, certificate, peer):
            transport = ManagedHTTPTransport(http2=True, manager=ConnectionManager(),
                verify=ssl.create_default_context(cafile=certificate))
            with httpx.Client(transport=transport, trust_env=False) as client, timeline.installed():
                with ThreadPoolExecutor(max_workers=4) as workers:
                    responses = list(workers.map(lambda i: client.get(url + "?Signature=secret",
                        headers={"Range": f"bytes={i * 32768}-{(i + 1) * 32768 - 1}"}).content, range(4)))
                self.assertEqual(b"".join(responses), payload)
        artifact = timeline.artifact()
        data = [e for e in artifact["stream_events"] if e["event_type"] == "DataReceived"]
        self.assertEqual(sum(e["bytes"] for e in data), len(payload))
        self.assertEqual(len({(e["protocol_connection_id"], e["stream_id"]) for e in data}), 4)
        for event in data:
            self.assertLessEqual(event["enqueued_ns"], event["dequeued_ns"])
            self.assertLessEqual(event["dequeued_ns"], event["body_yield_ns"])
            self.assertLessEqual(event["body_yield_ns"], event["sync_bridge_return_ns"])
            self.assertIsNotNone(event["dequeued_by_request_id"])
        self.assertNotIn("secret", json.dumps(artifact))

    def test_reset_and_cancellation_preserve_errors_and_remove_waiters(self):
        import h2.events
        import httpcore
        from benchmark.diagnostics.http2_stream_timeline import StreamTimeline
        timeline = StreamTimeline()

        async def check():
            async with ready_stream_scenario(timeline=timeline) as (connection, stream, tasks):
                tasks[5].cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await tasks[5]
                number = timeline._track(connection)
                self.assertNotIn((number, 5), timeline._stream_waiters)
                connection._events[7] = []
                reset = h2.events.StreamReset(stream_id=7, error_code=8)
                connection._events[7].append(reset)
                with self.assertRaises(httpcore.RemoteProtocolError):
                    await connection._receive_stream_event(httpcore.Request("GET", "https://example.test/7"), 7)
                self.assertNotIn((number, 7), timeline._stream_waiters)
        with timeline.installed():
            asyncio.run(check())
        self.assertTrue(any(e.get("error_type") == "RemoteProtocolError" for e in timeline.stream_events))

    def test_event_timeline_measures_ready_but_blocked_time_and_restores_queues(self):
        from benchmark.diagnostics.http2_stream_timeline import StreamTimeline
        timeline = StreamTimeline()
        observed = []

        async def check():
            async with ready_stream_scenario(timeline=timeline) as (connection, stream, tasks):
                observed.append(connection)
                record = next(e for e in timeline.stream_events
                              if e["stream_id"] == 5 and e["event_type"] == "DataReceived")
                self.assertTrue(record["consumer_waiting_at_enqueue"])
                self.assertNotIn("dequeued_ns", record)
                await asyncio.sleep(0.04)
                stream.release[1].set()
                self.assertEqual((await asyncio.wait_for(tasks[5], 3)).data, b"ready")
                self.assertGreater(record["ready_with_waiting_consumer_ns"], 30_000_000)
                self.assertEqual(record["enqueued_by_stream_id"], 1)
                self.assertGreaterEqual(record["stream_return_ns"], record["dequeued_ns"])
        with timeline.installed():
            asyncio.run(check())
        self.assertIs(type(observed[0]._events), dict)
        self.assertTrue(all(type(queue) is list for queue in observed[0]._events.values()))

    def test_buffered_data_without_a_waiter_is_not_counted_as_blocked(self):
        from benchmark.diagnostics.http2_stream_timeline import StreamTimeline
        timeline = StreamTimeline()

        async def check():
            async with ready_stream_scenario(timeline=timeline) as (connection, stream, tasks):
                # StreamEnded follows DATA but has no consumer until requested.
                stream.release[1].set()
                await asyncio.gather(*tasks.values())
                await asyncio.sleep(0.04)
                import httpcore
                with timeline.request("controlled", "GET", "https://example.test/5"):
                    event = await connection._receive_stream_event(
                        httpcore.Request("GET", "https://example.test/5"), 5)
                self.assertEqual(type(event).__name__, "StreamEnded")
                record = next(e for e in timeline.stream_events
                              if e["stream_id"] == 5 and e["event_type"] == "StreamEnded")
                self.assertGreater(record["queue_residence_ns"], 30_000_000)
                receive = timeline.stream_receives[record["receive_call_id"] - 1]
                self.assertEqual(record["ready_with_waiting_consumer_ns"],
                                 record["dequeued_ns"] - receive["start_ns"])
                self.assertGreater(receive["start_ns"] - record["enqueued_ns"], 30_000_000)
        with timeline.installed():
            asyncio.run(check())

    def test_ready_stream_waits_behind_an_unrelated_socket_read(self):
        async def check():
            async with ready_stream_scenario() as (connection, stream, tasks):
                self.assertEqual(connection._events[5][0].data, b"ready")
                self.assertFalse(tasks[5].done())
                self.assertFalse(tasks[3].done())
                self.assertEqual(stream.reads, 2)
                # No new input is needed for stream 5, yet it cannot consume it.
                stream.release[1].set()
                results = await asyncio.wait_for(asyncio.gather(tasks[1], tasks[3], tasks[5]), 3)
                self.assertEqual([event.data for event in results], [b"reader", b"later", b"ready"])
        asyncio.run(check())

    def test_ready_stream_first_in_lock_queue_finishes_without_later_input(self):
        async def check():
            async with ready_stream_scenario(order=(5, 3)) as (connection, stream, tasks):
                self.assertTrue(tasks[5].done())
                self.assertEqual(tasks[5].result().data, b"ready")
                self.assertFalse(tasks[3].done())
                self.assertFalse(stream.release[1].is_set())
        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
