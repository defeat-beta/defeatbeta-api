"""Process-wide physical connections with atomic HTTP stream reservations.

Only allocation and lifecycle management live here. httpcore still implements
TCP, TLS, proxies, HTTP framing, flow control, and GOAWAY handling. The private
adapter targets httpx 0.28.1 and httpcore 1.0.9; dependency bounds enforce this.
"""

from collections import Counter
from dataclasses import dataclass, field
import math
import os
from threading import Condition, Event, Thread
import time

import h2.exceptions
import httpcore
import httpx
from httpcore._sync.http2 import HTTP2Connection
from httpcore._async.http2 import AsyncHTTP2Connection

from defeatbeta_api.client.http_runtime import ConnectionFactory
from defeatbeta_api.client.http2_receive import coordinate_receives


_HTTP2_TYPES = (HTTP2Connection, AsyncHTTP2Connection)


@dataclass(frozen=True)
class ConnectionPoolConfiguration:
    core_connections_per_origin: int = 4
    max_connections_for_all_origins: int = 16
    max_streams_per_connection: int | None = 4
    extra_connection_idle_timeout: float = 60.0
    max_connecting_per_origin: int = 4

    def __post_init__(self):
        for name in ("core_connections_per_origin", "max_connections_for_all_origins", "max_connecting_per_origin"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.core_connections_per_origin > self.max_connections_for_all_origins:
            raise ValueError("Core connections must not exceed the process connection budget")
        value = self.max_streams_per_connection
        if value is not None and (type(value) is not int or value < 1):
            raise ValueError("max_streams_per_connection must be None or a positive integer")
        value = self.extra_connection_idle_timeout
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("extra_connection_idle_timeout must be finite and nonnegative")


class _ReservedStreams:
    """The outer allocator already owns a slot until response.close().

    Avoid a second, hidden semaphore queue in httpcore. Its SETTINGS reductions
    otherwise acquire semaphore permits while holding the connection read lock,
    potentially preventing active responses from finishing. hyper-h2 retains
    its independent enforcement of the peer's protocol limit.
    """

    def acquire(self):
        pass

    def release(self):
        pass


class _AsyncReservedStreams:
    async def acquire(self):
        pass

    async def release(self):
        pass


def _protocol(connection):
    """Unwrap direct, CONNECT, forward-proxy, and SOCKS connections."""
    while hasattr(connection, "_connection"):
        child = connection._connection
        if child is None:
            return None
        connection = child
    return connection


@dataclass(eq=False)
class _Connection:
    number: int
    route: object
    origin: object
    raw: object
    reserved: int = 0
    ready: bool = False
    draining: bool = False
    closing: bool = False
    idle_since: float | None = None


@dataclass(eq=False)
class _Pending:
    route: object
    origin: object
    deadline: float | None = None
    connection: _Connection | None = None
    error: Exception | None = None
    event: Event = field(default_factory=Event)


class ConnectionManager:
    def __init__(self, configuration=None, clock=time.monotonic):
        self.configuration = configuration or ConnectionPoolConfiguration()
        self._clock = clock
        self._condition = Condition()
        self._connections = []
        self._pending = []
        self._next_number = 0
        self._reaper = None
        self._created = 0
        self._peak_connections = 0
        self._peak_reserved = 0
        self._wait_seconds = 0.0
        self._assignments = 0
        self._configuring = False
        self._dirty = False
        self._dispatches = 0
        self._close_errors = 0

    def _schedule(self):
        """Called under the condition; only the allocator worker scans the queue."""
        self._dirty = True
        if self._reaper is None and (self._connections or self._pending):
            self._reaper = Thread(target=self._reap, name="defeatbeta-http-pool", daemon=True)
            try:
                self._reaper.start()
            except BaseException:
                self._reaper = None
                raise
        self._condition.notify_all()

    def configure(self, configuration):
        with self._condition:
            if self._configuring or self._pending or any(c.reserved for c in self._connections):
                raise RuntimeError("Configure the process HTTP pool before starting concurrent queries")
            self._configuring = True
            while any(c.closing for c in self._connections):
                self._condition.wait()
            closing = [self._retire(c) for c in self._connections]
        try:
            self._close(closing)
            with self._condition:
                self.configuration = configuration
                self._created = self._peak_connections = self._peak_reserved = 0
                self._wait_seconds = 0.0
                self._assignments = 0
                self._dispatches = self._close_errors = 0
        finally:
            with self._condition:
                self._configuring = False
                self._schedule()

    def _capacity(self, connection):
        if connection.draining or not connection.ready:
            return 0
        protocol = _protocol(connection.raw)
        if isinstance(protocol, _HTTP2_TYPES):
            if not protocol.is_available():
                return 0
            limit = min(protocol._max_streams, protocol._h2_state.remote_settings.max_concurrent_streams)
            configured = self.configuration.max_streams_per_connection
            return limit if configured is None else min(limit, configured)
        return 1 if connection.raw.is_available() else 0

    def _retire(self, connection):
        connection.draining = True
        connection.closing = True
        return connection

    def _close(self, connections):
        first_error = None
        for connection in connections:
            try:
                connection.raw.close()
            except BaseException as exc:
                first_error = first_error or exc
                with self._condition:
                    self._close_errors += 1
            finally:
                with self._condition:
                    self._connections.remove(connection)
                    self._schedule()
        if first_error is not None:
            raise first_error

    def _idle_cleanup(self):
        closing = []
        groups = Counter()
        now = self._clock()
        for connection in self._connections:
            if connection.closing:
                continue
            if connection.ready and (connection.raw.is_closed()
                                     or not connection.reserved and connection.raw.has_expired()):
                connection.draining = True
            origin = connection.origin
            group = (id(connection.route), origin.scheme, origin.host, origin.port)
            groups[group] += not connection.draining
            extra = groups[group] > self.configuration.core_connections_per_origin
            expired = (extra and connection.idle_since is not None
                       and now - connection.idle_since >= self.configuration.extra_connection_idle_timeout)
            if not connection.reserved and (connection.draining or expired):
                closing.append(self._retire(connection))
        return closing

    def _dispatch(self):
        self._dispatches += 1
        closing = self._idle_cleanup()
        def group(route, origin):
            return id(route), origin.scheme, origin.host, origin.port

        backlog = Counter(group(p.route, p.origin) for p in self._pending
                          if p.connection is None and p.error is None and not p.route.closed
                          and (p.deadline is None or p.deadline > self._clock()))
        for pending in self._pending:
            if pending.connection is not None or pending.error is not None or pending.route.closed:
                continue
            if pending.deadline is not None and pending.deadline <= self._clock():
                continue
            same = [c for c in self._connections if c.route is pending.route
                    and c.origin == pending.origin and not c.draining]
            connecting = [c for c in same if not c.ready]
            ready = [c for c in same if c.ready]
            key = group(pending.route, pending.origin)
            # Estimate future capacity only for expansion sizing. Connecting
            # sockets still admit exactly one request until SETTINGS arrive.
            hint = max((self._capacity(c) for c in ready), default=1)
            future_slots = sum(max(0, hint - c.reserved) for c in connecting)
            parallel_limit = self.configuration.max_connecting_per_origin if ready else 1
            available = self._available(same)
            can_create = (len(connecting) < parallel_limit and not available
                          and backlog[key] > future_slots
                          and len(self._connections) < self.configuration.max_connections_for_all_origins)
            if can_create:
                try:
                    raw = pending.route.factory(pending.origin)
                except Exception as exc:
                    pending.error = exc
                    backlog[key] -= 1
                    pending.event.set()
                    continue
                self._next_number += 1
                connection = _Connection(self._next_number, pending.route, pending.origin, raw)
                self._connections.append(connection)
                self._created += 1
                self._peak_connections = max(self._peak_connections, len(self._connections))
            elif available:
                connection, _ = min(available, key=lambda item: (
                    item[0].reserved / item[1], item[0].number))
            else:
                if not connecting:
                    victim = next((c for c in self._connections if not c.reserved and not c.closing
                                   and (c.route is not pending.route or c.origin != pending.origin)), None)
                    if victim is not None:
                        closing.append(self._retire(victim))
                continue
            self._reserve(connection)
            backlog[key] -= 1
            pending.connection = connection
            pending.event.set()
        return closing

    def _available(self, same):
        # Protocol state changes on the I/O thread. Use the same positive
        # capacity for eligibility and ranking; httpcore handles a connection
        # that becomes unavailable after this reservation.
        capacities = [(c, self._capacity(c)) for c in same]
        core = capacities[:self.configuration.core_connections_per_origin]
        return ([item for item in core if item[0].reserved < item[1]]
                or [item for item in capacities if item[0].reserved < item[1]])

    def _reserve(self, connection):
        connection.reserved += 1
        connection.idle_since = None
        self._peak_reserved = max(self._peak_reserved, sum(c.reserved for c in self._connections))

    def acquire(self, route, origin, deadline):
        pending = None
        assigned = False
        started = self._clock()
        try:
            with self._condition:
                if route.closed:
                    raise RuntimeError("HTTP transport is closed")
                now = self._clock()
                if deadline is not None and deadline <= now:
                    raise httpcore.PoolTimeout("Timed out waiting for an HTTP connection or stream slot")
                if not self._pending and not self._configuring:
                    same = [c for c in self._connections if c.route is route and c.origin == origin and not c.draining]
                    needs_cleanup = any(
                        c.raw.is_closed() or not c.reserved and c.raw.has_expired()
                        or index >= self.configuration.core_connections_per_origin
                        and c.idle_since is not None
                        and now - c.idle_since >= self.configuration.extra_connection_idle_timeout
                        for index, c in enumerate(same))
                    available = [] if needs_cleanup else self._available(same)
                    if available:
                        connection, _ = min(available, key=lambda item: (
                            item[0].reserved / item[1], item[0].number))
                        self._reserve(connection)
                        waited = self._clock() - started
                        self._assignments += 1
                        self._wait_seconds += waited
                        return connection, waited
                pending = _Pending(route, origin, deadline)
                self._pending.append(pending)
                self._schedule()
            while True:
                with self._condition:
                    if route.closed:
                        raise RuntimeError("HTTP transport is closed")
                    remaining = None if deadline is None else deadline - self._clock()
                    if pending.error is not None:
                        raise pending.error
                    if pending.connection is not None:
                        assigned = True
                        self._assignments += 1
                        waited = self._clock() - started
                        self._wait_seconds += waited
                        return pending.connection, waited
                    if remaining is not None and remaining <= 0:
                        raise httpcore.PoolTimeout("Timed out waiting for an HTTP connection or stream slot")
                pending.event.wait(remaining)
        finally:
            if pending is not None:
                with self._condition:
                    # Removal and abandoned-assignment detection must be atomic
                    # with dispatch, including cancellation of Event.wait().
                    self._pending.remove(pending)
                    abandoned = pending.connection if not assigned else None
                    self._schedule()
                if abandoned is not None:
                    self.release(abandoned)

    def observe(self, connection, event):
        """Called at protocol trace boundaries, without holding pool I/O locks."""
        protocol = _protocol(connection.raw)
        if isinstance(protocol, _HTTP2_TYPES) and event == "http2.send_request_headers.started":
            # Initialization has acquired the first slot. All later allocation
            # is handled atomically by this manager, including SETTINGS changes.
            protocol._max_streams_semaphore = (
                _AsyncReservedStreams() if isinstance(protocol, AsyncHTTP2Connection) else _ReservedStreams())
            if isinstance(protocol, AsyncHTTP2Connection):
                coordinate_receives(protocol)
        if event == "http2.receive_remote_settings.complete":
            with self._condition:
                connection.ready = True
                self._schedule()

    def ready(self, connection):
        with self._condition:
            connection.ready = True
            self._schedule()

    def release(self, connection, *, retire=False):
        closing = []
        with self._condition:
            connection.reserved -= 1
            if retire:
                connection.draining = True
            if connection.reserved == 0:
                connection.idle_since = self._clock()
                protocol = _protocol(connection.raw)
                if (connection.draining or connection.route.closed or connection.raw.is_closed()
                        or isinstance(protocol, _HTTP2_TYPES) and not protocol.is_available()):
                    closing.append(self._retire(connection))
            self._schedule()
        self._close(closing)

    def close_route(self, route):
        with self._condition:
            route.closed = True
            for pending in self._pending:
                if pending.route is route:
                    pending.event.set()
            closing = []
            for connection in self._connections:
                if connection.route is route and not connection.closing:
                    connection.draining = True
                    if not connection.reserved:
                        closing.append(self._retire(connection))
            self._schedule()
        self._close(closing)

    def _reap(self):
        while True:
            with self._condition:
                if not self._connections and not self._pending:
                    self._reaper = None
                    return
                if self._configuring:
                    self._condition.wait()
                    continue
                already_closing = {c for c in self._connections if c.closing}
                failed = False
                try:
                    if self._dirty:
                        self._dirty = False
                        closing = self._dispatch()
                    else:
                        closing = self._idle_cleanup()
                except Exception as exc:
                    # Wake even waiters without deadlines. A future request
                    # can restart allocation; do not close sockets already
                    # owned by another background closer.
                    for pending in self._pending:
                        if pending.connection is None and pending.error is None:
                            pending.error = exc
                            pending.event.set()
                    self._reaper = None
                    closing = [c for c in self._connections
                               if c.closing and c not in already_closing]
                    self._condition.notify_all()
                    failed = True
                if not closing and not failed:
                    idle = any(c.idle_since is not None and not c.closing for c in self._connections)
                    timeout = max(0.05, min(60.0, self.configuration.extra_connection_idle_timeout)) if idle else None
                    self._condition.wait(timeout)
                    continue
            # Closing can wait on TLS or a proxy. Keep those sockets counted,
            # but let the allocator serve other ready connections meanwhile.
            if closing:
                Thread(target=self._close_background, args=(closing,),
                       name="defeatbeta-http-close", daemon=True).start()
            if failed:
                return

    def _close_background(self, connections):
        try:
            self._close(connections)
        except Exception:
            # _close attempts every socket and records failures.
            pass

    def snapshot(self):
        with self._condition:
            connections = []
            for connection in self._connections:
                protocol = _protocol(connection.raw)
                h2 = isinstance(protocol, _HTTP2_TYPES)
                connections.append({
                    "connection_id": connection.number,
                    "origin": str(connection.origin),
                    "protocol": "HTTP/2" if h2 else "HTTP/1.1" if connection.ready else None,
                    "state": "closing" if connection.closing else "draining" if connection.draining
                    else "connecting" if not connection.ready else "busy"
                    if connection.reserved >= self._capacity(connection) else "ready",
                    "reserved_streams": connection.reserved,
                    "peer_stream_limit": protocol._h2_state.remote_settings.max_concurrent_streams if h2 else None,
                    "effective_stream_limit": self._capacity(connection),
                })
            return {"configuration": vars(self.configuration).copy(), "connections": connections,
                    "pending_requests": sum(p.connection is None for p in self._pending),
                    "created_connections": self._created, "peak_connections": self._peak_connections,
                    "peak_reserved_streams": self._peak_reserved, "assignments": self._assignments,
                    "dispatches": self._dispatches, "close_errors": self._close_errors,
                    "pool_wait_seconds": self._wait_seconds}


class _ResponseStream:
    def __init__(self, stream, manager, connection):
        self._stream = stream
        self._manager = manager
        self._connection = connection
        self._closed = False

    def __iter__(self):
        try:
            yield from self._stream
        except BaseException:
            self.close()
            raise

    def close(self):
        if not self._closed:
            self._closed = True
            failed = False
            try:
                self._stream.close()
            except BaseException:
                failed = True
                raise
            finally:
                self._manager.release(self._connection, retire=failed)


class _RoutePool:
    def __init__(self, factory_pool, manager, socket_options=()):
        self._factory_pool = factory_pool
        self.factory = factory_pool.create_connection
        self.manager = manager
        self.closed = False
        self.socket_options = socket_options

    @property
    def connections(self):
        with self.manager._condition:
            return [c.raw for c in self.manager._connections if c.route is self]

    def handle_request(self, request):
        if request.url.scheme not in (b"http", b"https", b"ws", b"wss"):
            raise httpcore.UnsupportedProtocol("Request URL must use HTTP or HTTPS")
        timeout = request.extensions.get("timeout", {}).get("pool")
        deadline = None if timeout is None else self.manager._clock() + timeout
        original_trace = request.extensions.get("trace")
        total_wait = 0.0
        # A whole idle pool may have pending GOAWAY frames. Permit retiring
        # every stale physical connection plus one fresh attempt, while the
        # original pool deadline remains in force across all reassignments.
        attempt_limit = self.manager.configuration.max_connections_for_all_origins + 1
        for attempt in range(attempt_limit):
            connection, waited = self.manager.acquire(self, request.url.origin, deadline)
            total_wait += waited

            def trace(event, info):
                self.manager.observe(connection, event)
                if original_trace is not None:
                    return original_trace(event, info)

            routed = httpcore.Request(method=request.method, url=request.url, headers=request.headers,
                                      content=request.stream, extensions={**request.extensions, "trace": trace,
                                                                          "defeatbeta_socket_options": self.socket_options})
            try:
                response = connection.raw.handle_request(routed)
            except httpcore.ConnectionNotAvailable as exc:
                self.manager.release(connection, retire=True)
                if attempt + 1 == attempt_limit:
                    raise httpcore.RemoteProtocolError("No usable connection after bounded reassignment") from exc
                continue
            except httpcore.LocalProtocolError as exc:
                # SETTINGS may decrease after reservation but before HEADERS.
                # hyper-h2 rejects this before sending anything. Only bodyless
                # read operations can safely be reassigned here.
                rejected = bool(exc.args and isinstance(exc.args[0], h2.exceptions.TooManyStreamsError))
                self.manager.release(connection, retire=not rejected)
                if rejected and request.method in (b"GET", b"HEAD") and attempt + 1 < attempt_limit:
                    continue
                raise
            except BaseException:
                self.manager.release(connection, retire=True)
                raise
            self.manager.ready(connection)
            response.stream = _ResponseStream(response.stream, self.manager, connection)
            response.extensions["defeatbeta_pool"] = {"connection_id": connection.number,
                                                      "pool_wait_seconds": total_wait}
            return response

    def close(self):
        try:
            self.manager.close_route(self)
        finally:
            self._factory_pool.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


_MANAGER = ConnectionManager()


def _after_fork():
    # Parent threads and their locks do not survive in the child. Do not close
    # inherited protocol objects here: that could affect the parent's sockets.
    global _MANAGER
    _MANAGER = ConnectionManager(_MANAGER.configuration)


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork)


class ManagedHTTPTransport(httpx.HTTPTransport):
    def __init__(self, *args, manager=None, **kwargs):
        socket_options = tuple(kwargs.get("socket_options") or ())
        if socket_options:
            kwargs["socket_options"] = socket_options
        self._pool = _RoutePool(ConnectionFactory(*args, **kwargs), manager or _MANAGER, socket_options)


def configure_connection_pool(*, core_connections_per_origin=4, max_connections_for_all_origins=16,
                              max_streams_per_connection=4, extra_connection_idle_timeout=60.0,
                              max_connecting_per_origin=4):
    """Set process-wide policy before starting concurrent Ticker queries.

    All proxies, TLS trust configurations, and origins share the same budget.
    Reconfiguration closes idle connections and rejects active or queued work.
    """
    configuration = ConnectionPoolConfiguration(core_connections_per_origin, max_connections_for_all_origins,
                                                max_streams_per_connection, extra_connection_idle_timeout,
                                                max_connecting_per_origin)
    _MANAGER.configure(configuration)


def get_connection_pool_status():
    """Return a point-in-time snapshot without exposing proxy credentials or URLs."""
    return _MANAGER.snapshot()
