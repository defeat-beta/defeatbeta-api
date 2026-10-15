"""Verify physical connection allocation and stream reservations."""

from concurrent.futures import ThreadPoolExecutor
import gzip
import os
import select
import socket
import ssl
from threading import Barrier, Event, Lock, Thread
import time
from types import SimpleNamespace
import unittest
import warnings
from unittest.mock import patch

import h2.settings
import httpcore
import httpx
from httpcore._sync.http2 import HTTP2Connection

from defeatbeta_api.client.http_pool import (
    ConnectionManager, ConnectionPoolConfiguration, ManagedHTTPTransport, _Connection, _ResponseStream, _RoutePool,
    configure_connection_pool, get_connection_pool_status,
)

from defeatbeta_api.client.shared_resources import SharedHttpClient, close_network_resources
from defeatbeta_api.client.http_runtime import runtime as http_runtime
from test.http2_peer import http2_peer
from test.proxy_peer import connect_proxy


def wait_until(predicate, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("Expected state was not reached")


class FakeConnection:
    def __init__(self, origin, limit):
        self._connection = HTTP2Connection(origin, SimpleNamespace(close=lambda: None))
        self._connection._max_streams = limit
        self._connection._h2_state.remote_settings = h2.settings.Settings(
            client=False, initial_values={h2.settings.SettingCodes.MAX_CONCURRENT_STREAMS: limit})

    def is_available(self):
        return self._connection.is_available()

    def is_closed(self):
        return self._connection.is_closed()

    def has_expired(self):
        return False

    def close(self):
        self._connection.close()


class TestConnectionManager(unittest.TestCase):
    def setUp(self):
        self.origin = httpcore.Origin(b"https", b"cdn.test", 443)
        self.route = SimpleNamespace(closed=False, factory=lambda origin: FakeConnection(origin, 2))
        self.manager = ConnectionManager(ConnectionPoolConfiguration(2, 3))

    def tearDown(self):
        self.manager.close_route(self.route)

    def acquire(self, route=None, origin=None, timeout=1):
        return self.manager.acquire(route or self.route, origin or self.origin, time.monotonic() + timeout)[0]

    def test_idle_cleanup_accepts_unhashable_httpcore_origins(self):
        entry = _Connection(1, self.route, self.origin, FakeConnection(self.origin, 2), ready=True)
        self.manager._connections.append(entry)
        self.assertEqual(self.manager._idle_cleanup(), [])

    def test_capacity_change_after_selection_does_not_break_allocation(self):
        from defeatbeta_api.client.http_pool import _Pending

        for queued in (False, True):
            for change in ("error", "settings"):
                with self.subTest(queued=queued, change=change):
                    entry = _Connection(1, self.route, self.origin,
                                        FakeConnection(self.origin, 2), ready=True)
                    self.manager._connections = [entry]
                    available = self.manager._available

                    def change_capacity(same):
                        result = available(same)
                        protocol = entry.raw._connection
                        if change == "error":
                            protocol._connection_error = True
                        else:
                            protocol._h2_state.remote_settings = h2.settings.Settings(
                                client=False, initial_values={
                                    h2.settings.SettingCodes.MAX_CONCURRENT_STREAMS: 0})
                        return result

                    try:
                        with self.manager._condition, patch.object(
                                self.manager, "_available", change_capacity):
                            if queued:
                                pending = _Pending(self.route, self.origin)
                                self.manager._pending.append(pending)
                                self.manager._dispatch()
                                assigned = pending.connection
                            else:
                                assigned = self.acquire()
                            self.assertIs(assigned, entry)
                            self.assertEqual(entry.reserved, 1)
                    finally:
                        self.manager._pending.clear()
                        self.manager._connections.clear()
                        entry.raw.close()

    def test_allocator_failure_wakes_waiters_and_allows_next_request(self):
        dispatch = self.manager._dispatch
        calls = 0

        def fail_once():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("Injected allocator failure")
            return dispatch()

        with patch.object(self.manager, "_dispatch", fail_once):
            with self.assertRaisesRegex(RuntimeError, "Injected allocator failure"):
                self.acquire(timeout=0.2)
            entry = self.acquire()
            self.manager.release(entry)

    def test_known_capacity_allows_parallel_initialization_without_overbuilding(self):
        self.manager.configure(ConnectionPoolConfiguration(1, 8, 2))
        first = self.acquire()
        self.manager.ready(first)
        second = self.acquire()
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(self.acquire, timeout=3) for _ in range(4)]
            try:
                wait_until(lambda: sum(f.done() for f in futures) >= 2
                           and self.manager.snapshot()["pending_requests"] == 2, timeout=0.5)
                state = self.manager.snapshot()
                self.assertEqual(sum(c["state"] == "connecting" for c in state["connections"]), 2)
                self.assertEqual(len(state["connections"]), 3)
                self.assertEqual(state["pending_requests"], 2)
            finally:
                self.manager.release(second)
                self.manager.release(first)
                for future in futures:
                    entry = future.result(timeout=4)
                    self.manager.ready(entry)
                    self.manager.release(entry)

    def test_waiters_do_not_run_full_queue_dispatch(self):
        calls = []
        original = self.manager._dispatch

        def dispatch():
            from threading import current_thread
            calls.append(current_thread().name)
            return original()

        with patch.object(self.manager, "_dispatch", dispatch):
            entry = self.acquire()
            self.manager.ready(entry)
            self.manager.release(entry)
        self.assertTrue(calls)
        self.assertTrue(all(name == "defeatbeta-http-pool" for name in calls), calls)

    def test_ready_uncontended_slot_does_not_depend_on_worker_notification(self):
        first = self.acquire()
        self.manager.ready(first)
        self.manager.release(first)
        wait_until(lambda: not self.manager._dirty)
        with patch.object(self.manager, "_schedule", lambda: None):
            reused = self.acquire(timeout=0.05)
        self.assertIs(reused, first)
        self.manager.release(reused)

    def test_cancellation_racing_assignment_releases_the_reserved_slot(self):
        from threading import get_ident
        from defeatbeta_api.client import http_pool

        first = self.acquire()
        condition = self.manager._condition
        original_pending = http_pool._Pending
        owner = get_ident()
        armed = False

        def pending(*args):
            item = original_pending(*args)

            def interrupt(timeout):
                nonlocal armed
                armed = True
                raise KeyboardInterrupt()

            item.event.wait = interrupt
            return item

        class ConditionAtCancellation:
            def __enter__(inner):
                nonlocal armed
                result = condition.__enter__()
                if armed and get_ident() == owner:
                    armed = False
                    first.ready = True
                    self.manager._dispatch()
                return result

            def __exit__(inner, *args):
                return condition.__exit__(*args)

            def __getattr__(inner, name):
                return getattr(condition, name)

        self.manager._condition = ConditionAtCancellation()
        try:
            with patch.object(http_pool, "_Pending", pending), self.assertRaises(KeyboardInterrupt):
                self.acquire()
            self.assertEqual(first.reserved, 1)
            self.assertEqual(self.manager.snapshot()["pending_requests"], 0)
        finally:
            self.manager._condition = condition
            while first.reserved:
                self.manager.release(first)

    def test_parallel_initialization_limit_is_enforced_under_a_large_burst(self):
        self.manager.configure(ConnectionPoolConfiguration(1, 8, 1, max_connecting_per_origin=2))
        first = self.acquire()
        self.manager.ready(first)
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(self.acquire, timeout=3) for _ in range(6)]
            try:
                wait_until(lambda: self.manager.snapshot()["pending_requests"] == 4
                           and sum(f.done() for f in futures) == 2)
                state = self.manager.snapshot()
                self.assertEqual(sum(c["state"] == "connecting" for c in state["connections"]), 2)
                self.assertEqual(sum(f.done() for f in futures), 2)
            finally:
                self.manager.release(first)
                for future in futures:
                    entry = future.result(timeout=4)
                    self.manager.ready(entry)
                    self.manager.release(entry)

    def test_fifo_admission_and_route_close_wakes_remaining_waiters(self):
        self.manager.configure(ConnectionPoolConfiguration(1, 1, 1))
        first = self.acquire()
        self.manager.ready(first)
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = []
            for index in range(3):
                futures.append(executor.submit(self.acquire, timeout=3))
                wait_until(lambda: self.manager.snapshot()["pending_requests"] == index + 1)
            self.manager.release(first)
            admitted = futures[0].result(timeout=1)
            self.assertFalse(futures[1].done())
            self.assertFalse(futures[2].done())
            self.manager.close_route(self.route)
            for future in futures[1:]:
                with self.assertRaisesRegex(RuntimeError, "closed"):
                    future.result(timeout=1)
            self.manager.release(admitted)
        self.assertEqual(self.manager.snapshot()["pending_requests"], 0)
        self.assertEqual(self.manager.snapshot()["connections"], [])

    def test_batch_close_failure_does_not_strand_other_connections(self):
        self.manager.configure(ConnectionPoolConfiguration(1, 2, 1))
        first = self.acquire()
        self.manager.ready(first)
        second = self.acquire()
        self.manager.ready(second)
        self.manager.release(first)
        self.manager.release(second)
        with patch.object(first.raw, "close", side_effect=ValueError("Close failed")):
            with self.assertRaises(ValueError):
                self.manager.close_route(self.route)
        self.assertTrue(second.raw.is_closed())
        self.assertEqual(self.manager.snapshot()["connections"], [])

    def test_slow_idle_close_does_not_block_other_ready_origin(self):
        self.manager.configure(ConnectionPoolConfiguration(1, 3, 1))
        first = self.acquire()
        self.manager.ready(first)
        second = self.acquire()
        self.manager.ready(second)
        other = SimpleNamespace(closed=False, factory=self.route.factory)
        origin = httpcore.Origin(b"https", b"other.test", 443)
        usable = self.acquire(other, origin)
        self.manager.ready(usable)
        self.manager.release(usable)
        self.manager.release(second)
        entered, finish = Event(), Event()
        original = second.raw.close

        def close():
            entered.set()
            finish.wait(2)
            original()

        second.raw.close = close
        try:
            with self.manager._condition:
                second.idle_since = time.monotonic() - 120
                self.manager._condition.notify_all()
            self.assertTrue(entered.wait(1))
            reused = self.acquire(other, origin, timeout=0.2)
            self.assertIs(reused, usable)
            self.manager.release(reused)
        finally:
            finish.set()
            self.manager.release(first)
            self.manager.close_route(other)


    @unittest.skipUnless(hasattr(os, "fork"), "POSIX fork is required")
    def test_fork_resets_global_allocator_without_acquiring_inherited_lock(self):
        from defeatbeta_api.client import http_pool

        entered, finish = Event(), Event()

        def hold():
            with self.manager._condition:
                entered.set()
                finish.wait(5)

        reader, writer = os.pipe()
        thread = Thread(target=hold)
        thread.start()
        self.assertTrue(entered.wait(1))
        try:
            with patch.object(http_pool, "_MANAGER", self.manager):
                child = os.fork()
                if child == 0:
                    try:
                        os.close(reader)
                        state = http_pool.get_connection_pool_status()
                        ok = not state["connections"] and state["configuration"]["max_connections_for_all_origins"] == 3
                        os.write(writer, b"ok" if ok else b"bad")
                    finally:
                        os._exit(0)
                os.close(writer)
                readable, _, _ = select.select([reader], [], [], 2)
                if not readable:
                    import signal
                    os.kill(child, signal.SIGKILL)
                os.waitpid(child, 0)
                self.assertTrue(readable, "Child allocator inherited a locked parent condition")
                self.assertEqual(os.read(reader, 3), b"ok")
        finally:
            os.close(reader)
            finish.set()
            thread.join(timeout=2)

    def test_atomic_reservations_respect_stream_and_process_limits(self):
        release = Event()

        def request(_):
            entry = self.acquire(timeout=4)
            self.manager.ready(entry)
            try:
                release.wait(3)
                return entry.number
            finally:
                self.manager.release(entry)

        with ThreadPoolExecutor(max_workers=24) as executor:
            futures = [executor.submit(request, n) for n in range(24)]
            try:
                wait_until(lambda: self.manager.snapshot()["peak_reserved_streams"] == 6)
                status = self.manager.snapshot()
                self.assertEqual(status["peak_connections"], 3)
                self.assertTrue(all(c["reserved_streams"] <= 2 for c in status["connections"]))
                self.assertGreater(status["pending_requests"], 0)
            finally:
                release.set()
            self.assertEqual(len([future.result(timeout=4) for future in futures]), 24)
        self.assertEqual(self.manager.snapshot()["pending_requests"], 0)

    def test_connecting_connection_is_coordinated(self):
        first = self.acquire()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.acquire)
            try:
                wait_until(lambda: self.manager.snapshot()["pending_requests"] == 1)
                self.assertEqual(self.manager.snapshot()["created_connections"], 1)
                self.manager.ready(first)
                second = future.result(timeout=2)
                self.assertEqual(first.number, second.number)
                self.manager.release(second)
            finally:
                self.manager.release(first)

    def test_core_connections_balance_and_sequential_requests_reuse(self):
        first = self.acquire()
        self.manager.ready(first)
        second = self.acquire()
        self.assertEqual(first.number, second.number)
        third = self.acquire()
        self.manager.ready(third)
        fourth = self.acquire()
        self.assertEqual([first.reserved, third.reserved], [2, 2])
        for entry in (third, fourth, second, first):
            self.manager.release(entry)
        reused = self.acquire()
        self.assertEqual(reused.number, first.number)
        self.manager.release(reused)
        self.assertEqual(self.manager.snapshot()["created_connections"], 2)

    def test_available_stream_does_not_make_a_request_pay_for_core_growth(self):
        first = self.acquire()
        self.manager.ready(first)
        second = self.acquire()
        try:
            self.assertEqual(first.number, second.number)
            self.assertEqual(self.manager.snapshot()["created_connections"], 1)
        finally:
            self.manager.release(second)
            self.manager.release(first)

    def test_global_budget_includes_other_routes_and_origins(self):
        self.manager.configure(ConnectionPoolConfiguration(1, 1))
        other = SimpleNamespace(closed=False, factory=lambda origin: FakeConnection(origin, 2))
        origin = httpcore.Origin(b"https", b"other.test", 443)
        first = self.acquire()
        self.manager.ready(first)
        try:
            with self.assertRaises(httpcore.PoolTimeout):
                self.acquire(other, origin, timeout=0.02)
            self.assertEqual(self.manager.snapshot()["peak_connections"], 1)
            self.assertEqual(self.manager.snapshot()["pending_requests"], 0)
            self.manager.release(first)
            replacement = self.acquire(other, origin)
            self.assertTrue(first.raw.is_closed())
            self.assertEqual(self.manager.snapshot()["peak_connections"], 1)
            self.manager.release(replacement)
        finally:
            self.manager.close_route(other)

    def test_closing_connections_keep_their_budget_until_close_returns(self):
        self.manager.configure(ConnectionPoolConfiguration(1, 1))
        first = self.acquire()
        self.manager.ready(first)
        self.manager.release(first)
        entered, finish = Event(), Event()
        original = first.raw.close

        def slow_close():
            entered.set()
            finish.wait(3)
            original()

        first.raw.close = slow_close
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.manager.close_route, self.route)
            try:
                self.assertTrue(entered.wait(1))
                self.assertEqual(len(self.manager.snapshot()["connections"]), 1)
                self.assertEqual(self.manager.snapshot()["connections"][0]["state"], "closing")
            finally:
                finish.set()
            future.result(timeout=2)

    def test_settings_reduction_blocks_new_reservations_without_closing_active_work(self):
        self.manager.configure(ConnectionPoolConfiguration(1, 1))
        first = self.acquire()
        self.manager.ready(first)
        second = self.acquire()
        protocol = first.raw._connection
        protocol._max_streams = 1
        protocol._h2_state.remote_settings = h2.settings.Settings(
            client=False, initial_values={h2.settings.SettingCodes.MAX_CONCURRENT_STREAMS: 1})
        self.manager.observe(first, "http2.receive_remote_settings.complete")
        with self.assertRaises(httpcore.PoolTimeout):
            self.acquire(timeout=0.02)
        self.assertFalse(first.raw.is_closed())
        self.manager.release(second)
        with self.assertRaises(httpcore.PoolTimeout):
            self.acquire(timeout=0.02)
        self.manager.release(first)
        resumed = self.acquire()
        self.manager.release(resumed)

    def test_client_stream_limit_is_distinct_from_peer_limit(self):
        self.manager.configure(ConnectionPoolConfiguration(1, 1, 1))
        first = self.acquire()
        self.manager.ready(first)
        status = self.manager.snapshot()["connections"][0]
        self.assertEqual(status["peer_stream_limit"], 2)
        self.assertEqual(status["effective_stream_limit"], 1)
        with self.assertRaises(httpcore.PoolTimeout):
            self.acquire(timeout=0.02)
        self.manager.release(first)

    def test_idle_extra_connections_shrink_without_network_activity(self):
        self.manager.configure(ConnectionPoolConfiguration(1, 3, 1, 0.02))
        entries = []
        for _ in range(3):
            entry = self.acquire()
            self.manager.ready(entry)
            entries.append(entry)
        self.manager.release(entries[2])
        wait_until(lambda: len(self.manager.snapshot()["connections"]) == 2)
        self.assertFalse(entries[0].raw.is_closed())
        self.assertFalse(entries[1].raw.is_closed())
        self.manager.release(entries[1])
        wait_until(lambda: len(self.manager.snapshot()["connections"]) == 1)
        self.manager.release(entries[0])

    def test_configuration_rejects_active_work(self):
        first = self.acquire()
        with self.assertRaises(RuntimeError):
            self.manager.configure(ConnectionPoolConfiguration())
        self.manager.release(first)

    def test_failed_connection_factory_leaves_no_queued_request_or_budget_leak(self):
        self.route.factory = lambda origin: (_ for _ in ()).throw(ValueError("Invalid connection"))
        with self.assertRaises(ValueError):
            self.acquire()
        self.assertEqual(self.manager.snapshot()["connections"], [])
        self.assertEqual(self.manager.snapshot()["pending_requests"], 0)

    def test_factory_failure_still_closes_scheduled_idle_connections(self):
        self.manager.configure(ConnectionPoolConfiguration(1, 3, 1, 60))
        first = self.acquire()
        self.manager.ready(first)
        second = self.acquire()
        self.manager.ready(second)
        self.manager.release(second)
        second.idle_since = time.monotonic() - 120
        self.route.factory = lambda origin: (_ for _ in ()).throw(ValueError("Invalid connection"))
        try:
            with self.assertRaises(ValueError):
                self.acquire()
            wait_until(second.raw.is_closed)
            self.assertEqual(len(self.manager.snapshot()["connections"]), 1)
        finally:
            self.manager.release(first)

    def test_invalid_configuration_is_rejected(self):
        for changes in ({"core_connections_per_origin": 0}, {"core_connections_per_origin": True},
                        {"max_connections_for_all_origins": 1}, {"max_streams_per_connection": 0},
                        {"max_streams_per_connection": 1.5}, {"extra_connection_idle_timeout": -1},
                        {"max_connecting_per_origin": 0}, {"max_connecting_per_origin": True},
                        {"extra_connection_idle_timeout": float("nan")}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                ConnectionPoolConfiguration(**changes)

    def test_default_policy_serves_oversubscribed_requests_with_bounded_slots(self):
        self.manager = ConnectionManager()
        self.route.factory = lambda origin: FakeConnection(origin, 100)
        configuration = self.manager.configuration
        capacity = configuration.max_connections_for_all_origins * configuration.max_streams_per_connection
        release = Event()

        def fetch(_):
            entry = self.acquire(timeout=4)
            self.manager.ready(entry)
            try:
                release.wait(3)
            finally:
                self.manager.release(entry)

        with ThreadPoolExecutor(max_workers=capacity * 2) as executor:
            futures = [executor.submit(fetch, n) for n in range(capacity * 2)]
            try:
                wait_until(lambda: self.manager.snapshot()["peak_reserved_streams"] == capacity)
                state = self.manager.snapshot()
                self.assertEqual(state["peak_connections"], configuration.max_connections_for_all_origins)
                self.assertGreater(state["pending_requests"], 0)
                self.assertTrue(all(c["reserved_streams"] <= configuration.max_streams_per_connection
                                    for c in state["connections"]))
            finally:
                release.set()
            for future in futures:
                future.result(timeout=4)
        self.assertEqual(self.manager.snapshot()["pending_requests"], 0)

    def test_response_close_failure_retires_connection_and_releases_slot(self):
        entry = self.acquire()
        self.manager.ready(entry)
        stream = SimpleNamespace(close=lambda: (_ for _ in ()).throw(ValueError("Close failed")))
        response = _ResponseStream(stream, self.manager, entry)
        with self.assertRaises(ValueError):
            response.close()
        self.assertTrue(entry.raw.is_closed())
        self.assertEqual(self.manager.snapshot()["connections"], [])
        response.close()

    def test_persistent_connection_rejection_is_bounded_and_releases_budget(self):
        manager = ConnectionManager(ConnectionPoolConfiguration(1, 2, 1))

        def factory(origin):
            raw = FakeConnection(origin, 100)
            raw.handle_request = lambda request: (_ for _ in ()).throw(httpcore.ConnectionNotAvailable())
            return raw

        route = _RoutePool(SimpleNamespace(create_connection=factory, close=lambda: None), manager)
        try:
            with self.assertRaises(httpcore.RemoteProtocolError):
                route.handle_request(httpcore.Request("GET", "https://cdn.test/file", extensions={"timeout": {"pool": 1}}))
            self.assertEqual(manager.snapshot()["created_connections"], 3)
            self.assertEqual(manager.snapshot()["connections"], [])
            self.assertEqual(manager.snapshot()["pending_requests"], 0)
        finally:
            route.close()


class TestHTTPPoolRegression(unittest.TestCase):
    def setUp(self):
        close_network_resources()
        configure_connection_pool()

    def tearDown(self):
        close_network_resources()
        configure_connection_pool()

    def test_buffered_large_responses_use_one_runtime_call_per_request(self):
        configure_connection_pool(core_connections_per_origin=1, max_connections_for_all_origins=2)
        payload = bytes(range(256)) * 4096
        with http2_peer(payload=payload, max_concurrent_streams=4) as (url, certificate, server), \
                patch.dict(os.environ, {"SSL_CERT_FILE": str(certificate)}):
            client = SharedHttpClient(proxy="", timeout=15)
            try:
                self.assertEqual(client.get(url).content, payload)
                server.release_responses.clear()
                runtime = http_runtime()
                original = runtime.call
                calls, guard = [], Lock()

                def observe(coroutine):
                    with guard:
                        calls.append(getattr(coroutine, "__qualname__", type(coroutine).__name__))
                    return original(coroutine)

                with patch.object(runtime, "call", observe), ThreadPoolExecutor(max_workers=16) as executor:
                    futures = [executor.submit(client.get, url) for _ in range(16)]
                    try:
                        wait_until(lambda: get_connection_pool_status()["pending_requests"] == 8)
                        self.assertEqual(sum(c["reserved_streams"] for c in
                                             get_connection_pool_status()["connections"]), 8)
                    finally:
                        server.release_responses.set()
                    try:
                        responses = [future.result(timeout=15).content for future in futures]
                    except Exception as exc:
                        self.fail(f"Request failed: {type(exc).__name__}; peer errors: {server.errors}")
                    self.assertEqual(responses, [payload] * 16)
                self.assertEqual(calls, ["Connection._request"] * 16)
                state = get_connection_pool_status()
                self.assertEqual(state["pending_requests"], 0)
                self.assertTrue(all(c["reserved_streams"] == 0 for c in state["connections"]))
                self.assertEqual(server.connections, 2)
                self.assertEqual(client.get(url).content, payload)
            finally:
                client.close()

    def test_buffered_body_timeout_releases_slot_and_next_request_recovers(self):
        configure_connection_pool(core_connections_per_origin=1, max_connections_for_all_origins=1)
        with http2_peer(payload=b"delayed", body_delay=0.2) as (url, certificate, server), \
                patch.dict(os.environ, {"SSL_CERT_FILE": str(certificate)}):
            client = SharedHttpClient(proxy="", timeout=httpx.Timeout(3, read=0.05))
            try:
                with self.assertRaises(httpx.ReadTimeout):
                    client.get(url)
                state = get_connection_pool_status()
                self.assertEqual(state["pending_requests"], 0)
                self.assertEqual(state["connections"], [])
                self.assertEqual(client.get(url, timeout=3).content, b"delayed")
                self.assertEqual(get_connection_pool_status()["connections"][0]["reserved_streams"], 0)
            finally:
                client.close()

    def test_buffered_http2_keeps_decoding_redirects_and_incomplete_body_errors(self):
        payload = bytes(range(256)) * 4096
        compressed = gzip.compress(payload)

        def respond(request):
            path = request[b":path"]
            if request[b":method"] == b"HEAD":
                return 200, [("content-length", str(len(payload)))], b""
            if path == b"/redirect":
                return 302, [("location", "/gzip"), ("content-length", "0")], b""
            if path == b"/truncated":
                return 200, [("content-length", "8")], b"partial"
            if path == b"/gzip":
                return 200, [("content-length", str(len(compressed))), ("content-encoding", "gzip")], compressed
            return 200, [("content-length", "0")], b""

        with http2_peer(response=respond) as (url, certificate, _), \
                patch.dict(os.environ, {"SSL_CERT_FILE": str(certificate)}):
            client = SharedHttpClient(proxy="", timeout=3)
            url = url.removesuffix("/file")
            try:
                response = client.get(url + "/redirect", follow_redirects=True)
                self.assertEqual(response.http_version, "HTTP/2")
                self.assertEqual(response.content, payload)
                self.assertEqual([item.status_code for item in response.history], [302])
                self.assertEqual(client.get(url + "/empty").content, b"")
                self.assertEqual(client.head(url).content, b"")
                with self.assertRaisesRegex(httpx.ProtocolError, "InvalidBodyLengthError"):
                    client.get(url + "/truncated")
                self.assertEqual(get_connection_pool_status()["pending_requests"], 0)
                self.assertEqual(client.get(url + "/gzip").content, payload)
                self.assertTrue(all(c["reserved_streams"] == 0 for c in get_connection_pool_status()["connections"]))
            finally:
                client.close()
                close_network_resources()

    def test_full_http2_connection_allocates_another_physical_connection(self):
        close_network_resources()
        with http2_peer(max_concurrent_streams=1, response_delay=0.05) as (
                url, certificate, server), patch.dict(os.environ, {"SSL_CERT_FILE": str(certificate)}):
            client = SharedHttpClient(proxy="", timeout=5)
            self.assertEqual(client.get(url).content, b"x")
            barrier = Barrier(4)

            def fetch(_):
                barrier.wait(timeout=3)
                return client.get(url).content

            with ThreadPoolExecutor(max_workers=4) as executor:
                self.assertEqual(list(executor.map(fetch, range(4))), [b"x"] * 4)
            self.assertGreaterEqual(server.connections, 2)

    def test_real_settings_reduction_does_not_deadlock_active_responses(self):
        configure_connection_pool(core_connections_per_origin=1, max_connections_for_all_origins=1)
        with http2_peer(max_concurrent_streams=4, settings_change_after=4,
                        changed_stream_limit=1) as (url, certificate, server), patch.dict(
                os.environ, {"SSL_CERT_FILE": str(certificate)}):
            trace_errors = []
            def trace(event, info):
                if event.endswith(".failed"):
                    trace_errors.append((event, repr(info.get("exception"))))
            client = SharedHttpClient(proxy="", timeout=3)
            self.assertEqual(client.get(url, extensions={"trace": trace}).content, b"x")
            server.release_responses.clear()
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(client.get, url, extensions={"trace": trace}) for _ in range(3)]
                try:
                    self.assertTrue(server.settings_changed.wait(2), f"Peer errors: {server.errors}")
                    def reduced():
                        failures = [repr(f.exception()) for f in futures if f.done() and f.exception() is not None]
                        if failures:
                            time.sleep(0.02)
                        self.assertFalse(failures, f"Request errors: {failures}; peer errors: {server.errors}; traces: {trace_errors}")
                        connections = get_connection_pool_status()["connections"]
                        return bool(connections and connections[0]["effective_stream_limit"] == 1)
                    wait_until(reduced)
                    self.assertEqual(get_connection_pool_status()["connections"][0]["reserved_streams"], 3)
                finally:
                    server.release_responses.set()
                self.assertEqual([f.result(timeout=4).content for f in futures], [b"x"] * 3)
            self.assertEqual(client.get(url).content, b"x")
            self.assertEqual(server.connections, 1)

    def test_default_pool_serves_128_concurrent_ranges_with_bounded_queue(self):
        manager = ConnectionManager()
        with http2_peer(max_concurrent_streams=100) as (url, certificate, server):
            transport = ManagedHTTPTransport(
                http2=True, verify=ssl.create_default_context(cafile=str(certificate)), manager=manager)
            with httpx.Client(transport=transport, trust_env=False, timeout=15) as client:
                self.assertEqual(client.get(url).content, b"x")
                server.release_responses.clear()
                barrier = Barrier(128)

                def fetch(index):
                    barrier.wait(timeout=10)
                    return client.get(url + ("/price" if index % 2 else "/profile")).content

                with ThreadPoolExecutor(max_workers=128) as executor:
                    futures = [executor.submit(fetch, index) for index in range(128)]
                    try:
                        def fully_queued():
                            state = manager.snapshot()
                            return (sum(c["reserved_streams"] for c in state["connections"]) == 64
                                    and state["pending_requests"] == 64)

                        wait_until(fully_queued, timeout=10)
                        state = manager.snapshot()
                        self.assertEqual(len(state["connections"]), 16)
                        self.assertTrue(all(c["reserved_streams"] == 4 for c in state["connections"]))
                    finally:
                        server.release_responses.set()
                    self.assertEqual([f.result(timeout=15) for f in futures], [b"x"] * 128)
                self.assertEqual(manager.snapshot()["pending_requests"], 0)
                self.assertEqual(manager.snapshot()["peak_connections"], 16)
                self.assertEqual(manager.snapshot()["peak_reserved_streams"], 64)

    def test_all_idle_core_goaways_are_retired_before_opening_a_fresh_connection(self):
        configure_connection_pool(core_connections_per_origin=4, max_streams_per_connection=1)
        with http2_peer(idle_retirement=0.4, response_delay=0.05) as (url, certificate, server), patch.dict(
                os.environ, {"SSL_CERT_FILE": str(certificate)}):
            client = SharedHttpClient(proxy="", timeout=3)
            self.assertEqual(client.get(url).content, b"x")
            barrier = Barrier(4)

            def fetch(_):
                barrier.wait(timeout=3)
                return client.get(url).content

            with ThreadPoolExecutor(max_workers=4) as executor:
                self.assertEqual(list(executor.map(fetch, range(4))), [b"x"] * 4)
            self.assertEqual(server.connections, 4)
            time.sleep(0.55)
            self.assertEqual(server.connections, 4)
            self.assertEqual(client.get(url).content, b"x")
            self.assertEqual(server.connections, 5)

    def test_streaming_response_holds_slot_until_close_and_timeout_removes_waiter(self):
        manager = ConnectionManager(ConnectionPoolConfiguration(1, 1, 1))
        with http2_peer() as (url, certificate, server):
            context = ssl.create_default_context(cafile=str(certificate))
            with httpx.Client(transport=ManagedHTTPTransport(verify=context, http2=True, manager=manager),
                              trust_env=False) as client:
                with client.stream("GET", url) as response:
                    self.assertEqual(response.status_code, 206)
                    self.assertEqual(manager.snapshot()["connections"][0]["reserved_streams"], 1)
                    with self.assertRaises(httpx.PoolTimeout):
                        client.get(url, timeout=httpx.Timeout(1, pool=0.02))
                    self.assertEqual(manager.snapshot()["pending_requests"], 0)
                self.assertEqual(client.get(url).content, b"x")
                self.assertEqual(manager.snapshot()["connections"][0]["reserved_streams"], 0)
                self.assertEqual(server.connections, 1)

    def test_connect_proxy_coordinates_cold_connections_and_uses_os_keepalive(self):
        manager = ConnectionManager(ConnectionPoolConfiguration(2, 2, 1))
        with http2_peer(response_delay=0.03) as (url, certificate, server), connect_proxy() as (proxy, proxy_server):
            context = ssl.create_default_context(cafile=str(certificate))
            transport = ManagedHTTPTransport(verify=context, http2=True, proxy=proxy, manager=manager,
                                            socket_options=[(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)])
            with httpx.Client(transport=transport, trust_env=False) as client:
                barrier = Barrier(8)

                def fetch(_):
                    barrier.wait(timeout=3)
                    response = client.get(url)
                    sock = response.extensions["network_stream"].get_extra_info("socket")
                    return response.content, bool(sock.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE))

                with ThreadPoolExecutor(max_workers=8) as executor:
                    self.assertEqual(list(executor.map(fetch, range(8))), [(b"x", True)] * 8)
                self.assertEqual(proxy_server.tunnels, 2)
                self.assertEqual(server.connections, 2)
                self.assertEqual(manager.snapshot()["peak_connections"], 2)

    def test_connect_proxy_and_direct_connections_share_one_budget(self):
        manager = ConnectionManager(ConnectionPoolConfiguration(1, 1))
        with http2_peer() as (url, certificate, server), connect_proxy() as (proxy, proxy_server):
            context = ssl.create_default_context(cafile=str(certificate))
            with httpx.Client(transport=ManagedHTTPTransport(verify=context, http2=True, manager=manager),
                              trust_env=False) as direct, httpx.Client(transport=ManagedHTTPTransport(
                                  verify=context, http2=True, proxy=proxy, manager=manager), trust_env=False) as proxied:
                self.assertEqual(direct.get(url).content, b"x")
                self.assertEqual(proxied.get(url).content, b"x")
                self.assertEqual(manager.snapshot()["peak_connections"], 1)
                self.assertEqual(proxy_server.tunnels, 1)

    def test_unsupported_protocol_does_not_consume_connection_budget(self):
        manager = ConnectionManager()
        with httpx.Client(transport=ManagedHTTPTransport(manager=manager), trust_env=False) as client:
            with self.assertRaises(httpx.UnsupportedProtocol):
                client.get("ftp://invalid.test/file")
        self.assertEqual(manager.snapshot()["created_connections"], 0)

    def test_async_trace_callback_is_rejected_by_the_sync_protocol_stack(self):
        async def trace(event, info):
            pass

        manager = ConnectionManager()
        with http2_peer() as (url, certificate, server):
            context = ssl.create_default_context(cafile=str(certificate))
            with httpx.Client(transport=ManagedHTTPTransport(verify=context, http2=True, manager=manager),
                              trust_env=False) as client, warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                with self.assertRaises(TypeError):
                    client.get(url, extensions={"trace": trace})
        self.assertEqual(manager.snapshot()["connections"], [])


if __name__ == "__main__":
    unittest.main()
