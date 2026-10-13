"""Observe decoded HTTP/2 event queues without changing their scheduling.

Queue timestamps describe protocol dispatch, not packet arrival. Instrumentation
is synchronous and never wakes a stream or bypasses the existing read lock.
Install and remove only when the observed protocol operations are quiescent.
"""

from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
from bisect import bisect_left
import functools
from unittest.mock import patch

from benchmark.diagnostics.cache_timeline import CacheTimeline


class _EventQueue(list):
    def __init__(self, values, timeline, connection_id, stream_id):
        super().__init__(values)
        self.original = values
        self.timeline = timeline
        self.connection_id = connection_id
        self.stream_id = stream_id
        self.records = [self._record(event, preexisting=True) for event in values]

    def _record(self, event, *, preexisting=False):
        timeline = self.timeline
        request = timeline.request_context.get()
        waiter = timeline._stream_waiters.get((self.connection_id, self.stream_id))
        reader = timeline._reader_context.get()
        record = {"id": len(timeline.stream_events) + 1,
                  "protocol_connection_id": self.connection_id, "stream_id": self.stream_id,
                  "event_type": type(event).__name__, "preexisting": preexisting,
                  "enqueued_ns": None if preexisting else timeline.now(),
                  "enqueued_by_request_id": request["id"] if request else None,
                  "enqueued_by_stream_id": reader,
                  "consumer_waiting_at_enqueue": waiter is not None}
        if type(event).__name__ == "DataReceived":
            record["bytes"] = len(event.data)
        timeline.stream_events.append(record)
        return record

    def append(self, event):
        record = self._record(event)
        super().append(event)
        self.records.append(record)

    def pop(self, index=-1):
        event = super().pop(index)
        record = self.records.pop(index)
        timeline = self.timeline
        now = timeline.now()
        request = timeline.request_context.get()
        record.update(dequeued_ns=now, dequeued_by_request_id=request["id"] if request else None,
                      dequeue_bridge_id=timeline.bridge_context.get())
        waiter = timeline._stream_waiters.get((self.connection_id, self.stream_id))
        if waiter is not None:
            waiter["event_id"] = record["id"]
            record["receive_call_id"] = waiter["id"]
        if record["enqueued_ns"] is not None:
            record["queue_residence_ns"] = now - record["enqueued_ns"]
            if waiter is not None:
                record["ready_with_waiting_consumer_ns"] = now - max(record["enqueued_ns"], waiter["start_ns"])
        if record["event_type"] == "DataReceived":
            timeline._last_data[(self.connection_id, self.stream_id)] = record
        return event


class _EventMap(dict):
    def __init__(self, values, timeline, connection_id):
        super().__init__()
        self.original = values
        self.timeline = timeline
        self.connection_id = connection_id
        for stream_id, queue in values.items():
            self[stream_id] = queue

    def __setitem__(self, stream_id, queue):
        super().__setitem__(stream_id, _EventQueue(queue, self.timeline, self.connection_id, stream_id))

    def restore(self):
        self.original.clear()
        for stream_id, queue in self.items():
            queue.original[:] = queue
            self.original[stream_id] = queue.original
        return self.original


class StreamTimeline(CacheTimeline):
    def __init__(self):
        super().__init__()
        self.stream_events = []
        self.stream_receives = []
        self._stream_connections = {}
        self._stream_waiters = {}
        self._last_data = {}
        self._reader_context = ContextVar("diagnostic_reading_stream", default=None)
        self._reader_connection_context = ContextVar("diagnostic_reading_connection", default=None)

    def event(self, phase, start, end, **details):
        if phase in {"transport.socket_read", "transport.async_h2_read_lock_wait"}:
            details["protocol_connection_id"] = self._reader_connection_context.get()
            details["reading_stream_id"] = self._reader_context.get()
        super().event(phase, start, end, **details)

    def _track(self, connection):
        if connection not in self._stream_connections:
            number = len(self._stream_connections) + 1
            queues = _EventMap(connection._events, self, number)
            connection._events = queues
            self._stream_connections[connection] = (number, queues)
        return self._stream_connections[connection][0]

    def artifact(self):
        from benchmark.workloads.http_pool_mixed import distribution

        result = super().artifact()
        bridges = {bridge["id"]: bridge for bridge in self.bridges}
        reads = {}
        locks = {}
        for span in self.events:
            if span["phase"] == "transport.socket_read" and span.get("protocol_connection_id") is not None:
                reads.setdefault(span["protocol_connection_id"], []).append(span)
            elif span["phase"] == "transport.async_h2_read_lock_wait":
                locks.setdefault(span.get("bridge_id"), []).append(span)
        for spans in reads.values():
            spans.sort(key=lambda span: span["end_ns"])
        ends = {key: [span["end_ns"] for span in spans] for key, spans in reads.items()}
        for event in self.stream_events:
            bridge = bridges.get(event.get("dequeue_bridge_id"), {})
            if "body_yield_ns" in event and "end_ns" in bridge and "error_type" not in bridge:
                event["sync_bridge_return_ns"] = bridge["end_ns"]
                event["body_yield_to_sync_ns"] = bridge["end_ns"] - event["body_yield_ns"]
            if "ready_with_waiting_consumer_ns" in event:
                # Intersect known-ready time, this consumer's lock wait, and
                # another stream's socket read on the same physical protocol.
                start = event["dequeued_ns"] - event["ready_with_waiting_consumer_ns"]
                stop = event["dequeued_ns"]
                number = event["protocol_connection_id"]
                spans = reads.get(number, [])
                index = bisect_left(ends.get(number, []), start)
                overlap = []
                for read_span in spans[index:]:
                    if read_span["start_ns"] >= stop:
                        break
                    if read_span.get("reading_stream_id") == event["stream_id"]:
                        continue
                    for lock_span in locks.get(event.get("dequeue_bridge_id"), []):
                        if (lock_span.get("protocol_connection_id") != number
                                or lock_span.get("reading_stream_id") != event["stream_id"]):
                            continue
                        begin = max(start, read_span["start_ns"], lock_span["start_ns"])
                        end = min(stop, read_span["end_ns"], lock_span["end_ns"])
                        if end > begin:
                            overlap.append((begin, end))
                covered, previous = 0, -1
                for begin, end in sorted(overlap):
                    covered += max(0, end - max(begin, previous))
                    previous = max(previous, end)
                event["ready_blocked_by_other_read_ns"] = covered
        result["stream_events"] = self.stream_events
        result["stream_receives"] = self.stream_receives
        result["stream_summary"] = {
            kind: {key: distribution([event[key] / 1e9 for event in self.stream_events
                                     if event["event_type"] == kind and key in event])
                   for key in ("queue_residence_ns", "ready_with_waiting_consumer_ns",
                               "ready_blocked_by_other_read_ns", "body_yield_to_sync_ns")}
            for kind in sorted({event["event_type"] for event in self.stream_events})}
        result["methodology"]["stream_events"] = (
            "Protocol enqueue/dequeue, receive return, body yield and synchronous bridge return; not packet arrival")
        result["methodology"]["ready_wait"] = (
            "Enqueue-to-dequeue clipped to the consuming receive call; queue residence before consumer demand is excluded")
        return result

    @contextmanager
    def installed(self, *, filesystems=()):
        from httpcore._async.http2 import AsyncHTTP2Connection

        original_receive = AsyncHTTP2Connection._receive_stream_event
        original_read = AsyncHTTP2Connection._receive_events
        original_body = AsyncHTTP2Connection._receive_response_body

        @functools.wraps(original_receive)
        async def receive(connection, request, stream_id):
            number = self._track(connection)
            key = (number, stream_id)
            current = self.request_context.get()
            waiter = {"id": len(self.stream_receives) + 1, "protocol_connection_id": number,
                      "stream_id": stream_id, "request_id": current["id"] if current else None,
                      "bridge_id": self.bridge_context.get(), "start_ns": self.now(),
                      "queue_ready_at_start": bool(connection._events.get(stream_id))}
            self.stream_receives.append(waiter)
            self._stream_waiters[key] = waiter
            try:
                return await original_receive(connection, request, stream_id)
            except BaseException as exc:
                waiter["error_type"] = type(exc).__name__
                raise
            finally:
                waiter["end_ns"] = self.now()
                self._stream_waiters.pop(key, None)
                if "event_id" in waiter:
                    record = self.stream_events[waiter["event_id"] - 1]
                    record["stream_return_ns"] = waiter["end_ns"]
                    if "error_type" in waiter:
                        record["error_type"] = waiter["error_type"]

        @functools.wraps(original_read)
        async def read(connection, request, stream_id=None):
            number = self._track(connection)
            token = self._reader_context.set(stream_id)
            connection_token = self._reader_connection_context.set(number)
            try:
                return await original_read(connection, request, stream_id)
            finally:
                self._reader_context.reset(token)
                self._reader_connection_context.reset(connection_token)

        @functools.wraps(original_body)
        async def body(connection, request, stream_id):
            number = self._track(connection)
            iterator = original_body(connection, request, stream_id)
            try:
                async for chunk in iterator:
                    record = self._last_data.pop((number, stream_id), None)
                    if record is not None:
                        record["body_yield_ns"] = self.now()
                    yield chunk
            finally:
                await iterator.aclose()

        with super().installed(filesystems=filesystems), ExitStack() as stack:
            stack.enter_context(patch.object(AsyncHTTP2Connection, "_receive_stream_event", receive))
            stack.enter_context(patch.object(AsyncHTTP2Connection, "_receive_events", read))
            stack.enter_context(patch.object(AsyncHTTP2Connection, "_receive_response_body", body))
            try:
                yield self
            finally:
                for connection, (_, queues) in self._stream_connections.items():
                    if connection._events is queues:
                        connection._events = queues.restore()
