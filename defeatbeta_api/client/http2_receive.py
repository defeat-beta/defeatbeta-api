"""Coordinate demand-driven receives on our pinned async httpcore connections.

httpcore 1.0.9 owns framing, dispatch, flow control and socket timeouts. Only
one caller enters its receive operation at a time. Other callers await a
notification and recheck their own predicate instead of queuing for its read
lock. No reader task, prefetch buffer or periodic network traffic is created.
All methods run on the process HTTP runtime's single asyncio event loop.
"""

import asyncio

import httpcore


class _ReceiveCoordinator:
    def __init__(self, connection):
        self.connection = connection
        # Resolve class methods at call time so a long-lived connection never
        # retains an expired diagnostic hook installed during its creation.
        self.protocol = type(connection)
        self.reading = False
        self.closed = False
        self.failure = None
        self.changed = asyncio.Event()

    def notify(self):
        # Replace before waking: a subsequent wait must observe the next change.
        changed, self.changed = self.changed, asyncio.Event()
        changed.set()

    def check_open(self, stream_id):
        if self.closed or self.connection.is_closed():
            raise httpcore.ReadError("HTTP/2 connection is closed")
        if stream_id is not None and stream_id not in self.connection._events:
            raise httpcore.ReadError("HTTP/2 response stream is closed")
        if self.failure is not None:
            raise self.failure

    async def receive(self, request, stream_id=None):
        while True:
            self.check_open(stream_id)
            if not self.reading:
                # There is no suspension between checking and claiming ownership.
                self.reading = True
                try:
                    return await self.protocol._receive_events(self.connection, request, stream_id)
                except Exception as exc:
                    if self.connection._connection_terminated is None:
                        # A shared read/dispatch/write failure ends this receiver.
                        # Cancellation is not an Exception and leaves ownership
                        # transferable. GOAWAY remains classified by httpcore.
                        self.failure = exc
                        self.connection._connection_error = True
                    raise
                finally:
                    self.reading = False
                    self.notify()

            changed = self.changed
            await changed.wait()
            self.check_open(stream_id)
            if self.connection._connection_terminated is None:
                # Both response consumers and outgoing-flow waiters already loop
                # over their own predicates. Let them inspect the updated state
                # even if another caller has started the next socket read.
                return
            # Preserve httpcore's per-stream GOAWAY classification instead of
            # duplicating last_stream_id and retry accounting here.

    async def response_closed(self, stream_id):
        try:
            await self.protocol._response_closed(self.connection, stream_id)
        finally:
            self.notify()

    async def close(self):
        self.closed = True
        self.notify()
        await self.protocol.aclose(self.connection)


def coordinate_receives(connection):
    """Install once on an owned connection, before its first HTTP/2 receive."""
    if hasattr(connection, "_defeatbeta_receive"):
        return
    coordinator = _ReceiveCoordinator(connection)
    connection._defeatbeta_receive = coordinator
    connection._receive_events = coordinator.receive
    connection._response_closed = coordinator.response_closed
    connection.aclose = coordinator.close
