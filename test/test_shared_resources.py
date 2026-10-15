"""Exercise resource sharing, failure recovery and ownership boundaries."""

from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
import json
import os
import hashlib
import gc
import errno
import multiprocessing
import tempfile
from pathlib import Path
from threading import Event, Lock
import time
import unittest
from types import SimpleNamespace
from weakref import WeakValueDictionary, ref
from unittest.mock import Mock, patch

import httpx
import requests
import duckdb

from defeatbeta_api.client.dataset_cache_fs import DatasetCacheFileSystem, DatasetVersionChanged
from defeatbeta_api.client.hf_session import MetadataSession
from defeatbeta_api.client.http_pool import get_connection_pool_status
from defeatbeta_api.client.duckdb_client import DuckDBClient
from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.client.hugging_face_client import HuggingFaceClient
from defeatbeta_api.client.shared_resources import (
    FOOTERS, PARQUET_INDEXES, SharedCache, SharedHttpClient, close_network_resources,
    network_identity,
)
from defeatbeta_api.client import shared_resources
from test.test_dataset_cache_fs import (
    FakeRangeClient, PINNED, SIGNED, FAKE_FOOTER_BYTES, local_range_server,
)
from test.http2_peer import http2_peer


def shared_footer_process(directory, url, total, start, messages):
    """Prepare one footer in a spawned process sharing only the disk cache."""
    filesystem = DatasetCacheFileSystem(
        directory=directory, version="footer-process-v1", http_proxy="",
        resolve=lambda pinned, refresh=False: (url, total))
    filesystem._clients[0].trust_env = True  # Trust the fixture CA on the explicit route.
    try:
        path = filesystem.register(PINNED)
        messages.put(("ready", None))
        if not start.wait(15):
            raise TimeoutError("Footer readers did not start together")
        size = filesystem.prepare_footer(path)
        messages.put(("result", (size, filesystem.cached_footer_bytes(path))))
    except Exception as exc:
        messages.put(("error", repr(exc)))
        raise
    finally:
        filesystem.close()
        close_network_resources()


def hold_file_lock_process(path, channel):
    """Hold a real OS lock until released or terminated by the parent."""
    try:
        channel.send("waiting")
        with shared_resources.file_lock(Path(path)):
            channel.send("acquired")
            channel.recv()
    finally:
        channel.close()


class TestSharedResources(unittest.TestCase):
    def test_complete_requests_select_buffering_without_mutating_caller_extensions(self):
        response = object()
        client = Mock()
        client.request.return_value = response

        @contextmanager
        def borrow(identity):
            yield client

        extensions = {"trace": Mock()}
        with patch.object(shared_resources, "network_client", borrow):
            handle = SharedHttpClient(proxy="", timeout=7)
            self.assertIs(handle.get("https://cdn.test/file", extensions=extensions), response)
        options = client.request.call_args.kwargs
        self.assertEqual(options["timeout"], 7)
        self.assertIs(options["extensions"]["trace"], extensions["trace"])
        self.assertTrue(options["extensions"]["defeatbeta_buffer_response"])
        self.assertEqual(list(extensions), ["trace"])

    def test_forced_refresh_during_result_publication_builds_a_new_value(self):
        published, finish = Event(), Event()

        class PausedPublication(Future):
            def set_result(self, value):
                super().set_result(value)
                if value == "old-url":
                    published.set()
                    if not finish.wait(5):
                        raise TimeoutError("Publication was not released")

        cache = SharedCache()
        build = Mock(side_effect=["old-url", "new-url"])
        with patch.object(shared_resources, "Future", PausedPublication), \
                ThreadPoolExecutor(max_workers=1) as executor:
            owner = executor.submit(cache.get_or_build, "file", build)
            try:
                self.assertTrue(published.wait(3))
                observed = cache.get_or_build("file", build)
                refreshed = cache.get_or_build("file", build, force_if=observed)
                self.assertEqual(refreshed, "new-url")
                self.assertEqual(build.call_count, 2)
            finally:
                finish.set()
            self.assertEqual(owner.result(timeout=3), "old-url")
        self.assertEqual(cache.get_or_build("file", build), "new-url")

    def tearDown(self):
        close_network_resources()

    def test_old_publisher_cannot_remove_a_new_pending_refresh(self):
        published, finish_old, building_new, finish_new = (Event() for _ in range(4))

        class PausedPublication(Future):
            def set_result(self, value):
                super().set_result(value)
                if value == "old":
                    published.set()
                    if not finish_old.wait(5):
                        raise TimeoutError("Old publisher was not released")

        def build_new():
            building_new.set()
            if not finish_new.wait(5):
                raise TimeoutError("New builder was not released")
            return "new"

        cache = SharedCache()
        with patch.object(shared_resources, "Future", PausedPublication), \
                ThreadPoolExecutor(max_workers=2) as executor:
            old = executor.submit(cache.get_or_build, "key", lambda: "old")
            try:
                self.assertTrue(published.wait(3))
                new = executor.submit(cache.get_or_build, "key", build_new, force_if="old")
                self.assertTrue(building_new.wait(3))
                finish_old.set()
                self.assertEqual(old.result(timeout=3), "old")
                with cache.lock:
                    self.assertIn("key", cache.pending)
                    self.assertFalse(cache.pending["key"].done())
            finally:
                finish_old.set()
                finish_new.set()
            self.assertEqual(new.result(timeout=3), "new")
        self.assertEqual(cache.pending, {})

    def test_failed_publication_allows_an_independent_retry(self):
        published, finish = Event(), Event()

        class PausedFailure(Future):
            def set_exception(self, exception):
                super().set_exception(exception)
                published.set()
                if not finish.wait(5):
                    raise TimeoutError("Failed publisher was not released")

        cache = SharedCache()
        with patch.object(shared_resources, "Future", PausedFailure), \
                ThreadPoolExecutor(max_workers=1) as executor:
            old = executor.submit(cache.get_or_build, "key", Mock(side_effect=ValueError("old failure")))
            try:
                self.assertTrue(published.wait(3))
                self.assertEqual(cache.get_or_build("key", lambda: "recovered"), "recovered")
            finally:
                finish.set()
            with self.assertRaisesRegex(ValueError, "old failure"):
                old.result(timeout=3)

    def test_windows_file_lock_waits_through_extended_contention(self):
        attempts = []

        def locking(fd, mode, length):
            attempts.append(mode)
            if mode == 1 or (mode == 2 and attempts.count(2) <= 12):
                raise OSError(errno.EACCES, "Lock is held by another process")

        windows = SimpleNamespace(LK_LOCK=1, LK_NBLCK=2, LK_UNLCK=3, locking=locking)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shared.lock"
            with patch.object(shared_resources, "os", SimpleNamespace(name="nt", fstat=os.fstat)), \
                    patch.dict("sys.modules", {"msvcrt": windows}), patch("time.sleep") as sleep:
                with shared_resources.file_lock(path):
                    self.assertEqual(attempts.count(2), 13)
                self.assertEqual(attempts[-1], windows.LK_UNLCK)
                self.assertEqual(sleep.call_count, 12)

    def test_windows_file_lock_propagates_unrelated_errors_and_unlocks_on_failure(self):
        windows = SimpleNamespace(LK_LOCK=1, LK_NBLCK=2, LK_UNLCK=3, locking=Mock())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shared.lock"
            with patch.object(shared_resources, "os", SimpleNamespace(name="nt", fstat=os.fstat)), \
                    patch.dict("sys.modules", {"msvcrt": windows}), patch("time.sleep") as sleep:
                windows.locking.side_effect = OSError(errno.EBADF, "Invalid handle")
                with self.assertRaises(OSError) as raised:
                    with shared_resources.file_lock(path):
                        self.fail("An invalid handle must not acquire a lock")
                self.assertEqual(raised.exception.errno, errno.EBADF)
                sleep.assert_not_called()
                self.assertEqual(windows.locking.call_count, 1)
                windows.locking.reset_mock(side_effect=True)
                with self.assertRaisesRegex(ValueError, "Preparation failed"):
                    with shared_resources.file_lock(path):
                        raise ValueError("Preparation failed")
                self.assertEqual(windows.locking.call_args.args[1], windows.LK_UNLCK)

    def test_footer_lock_identity_is_stable_across_dataset_versions(self):
        payload = b"PAR1" + b"x" * 100 + FAKE_FOOTER_BYTES
        remote = FakeRangeClient(len(payload), payload=payload)
        with tempfile.TemporaryDirectory() as directory:
            filesystem = DatasetCacheFileSystem(
                directory=directory, version="2026-10-01T00:00:00Z", http_client=remote,
                resolve=lambda url, refresh=False: (SIGNED, len(payload)))
            try:
                for day in range(1, 6):
                    filesystem.update_version(f"2026-10-{day:02}T00:00:00Z")
                    filesystem.prepare_footer(filesystem.register(PINNED))
                filesystem.cleanup_stale()
                self.assertEqual(len(list(Path(directory).glob("*.footer"))), 1)
                self.assertEqual(len(list(Path(directory).glob(".footer-*.lock"))), 1)
                self.assertEqual(len(remote.calls), 5)
            finally:
                filesystem.close()

    def test_file_lock_waits_over_ten_seconds_and_recovers_after_owner_termination(self):
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "shared.lock")
            owner_channel, owner_child = context.Pipe()
            waiter_channel, waiter_child = context.Pipe()
            owner = context.Process(target=hold_file_lock_process, args=(path, owner_child))
            waiter = context.Process(target=hold_file_lock_process, args=(path, waiter_child))
            started = []
            try:
                owner.start()
                started.append(owner)
                owner_child.close()
                for expected in ("waiting", "acquired"):
                    self.assertTrue(owner_channel.poll(20))
                    self.assertEqual(owner_channel.recv(), expected)
                waiter.start()
                started.append(waiter)
                waiter_child.close()
                self.assertTrue(waiter_channel.poll(20))
                self.assertEqual(waiter_channel.recv(), "waiting")
                self.assertFalse(waiter_channel.poll(11), "Waiter must remain blocked without failing")
                self.assertTrue(waiter.is_alive())
                owner.terminate()
                owner.join(timeout=5)
                self.assertFalse(owner.is_alive())
                self.assertTrue(waiter_channel.poll(10))
                self.assertEqual(waiter_channel.recv(), "acquired")
                waiter_channel.send("release")
                waiter.join(timeout=5)
                self.assertEqual(waiter.exitcode, 0)
                with shared_resources.file_lock(Path(path)):
                    self.assertTrue(Path(path).exists())
            finally:
                for process in started:
                    if process.is_alive():
                        process.terminate()
                    process.join(timeout=5)
                for channel in (owner_channel, owner_child, waiter_channel, waiter_child):
                    channel.close()

    def test_active_pool_cannot_be_evicted_or_closed(self):
        close_network_resources()
        with patch.object(shared_resources, "MAX_NETWORK_IDENTITIES", 1):
            with shared_resources.network_client((None, None, None)) as active:
                close_network_resources()
                self.assertFalse(active.is_closed)
                with self.assertRaises(httpx.PoolTimeout):
                    with shared_resources.network_client(("http://other.test", None, None)):
                        self.fail("An active resource must not be evicted")
            with shared_resources.network_client((None, None, None)) as reused:
                self.assertIs(reused, active)

    def test_failed_new_pool_preserves_previous_idle_resource(self):
        close_network_resources()
        with patch.object(shared_resources, "MAX_NETWORK_IDENTITIES", 1):
            with shared_resources.network_client((None, None, None)) as existing:
                pass
            with patch.object(shared_resources, "ManagedHTTPTransport", side_effect=ValueError("Invalid route")):
                with self.assertRaises(ValueError):
                    with shared_resources.network_client(("http://other.test", None, None)):
                        self.fail("Invalid pool creation must fail")
            with shared_resources.network_client((None, None, None)) as reused:
                self.assertIs(reused, existing)
                self.assertFalse(existing.is_closed)

    def test_eviction_close_failure_releases_new_pool_borrower(self):
        close_network_resources()
        identity = ("http://other.test", None, None)
        with patch.object(shared_resources, "MAX_NETWORK_IDENTITIES", 1):
            with shared_resources.network_client((None, None, None)) as existing:
                pass
            try:
                with patch.object(existing, "close", side_effect=ValueError("Close failed")):
                    with self.assertRaises(ValueError):
                        with shared_resources.network_client(identity):
                            self.fail("Failed eviction must propagate")
                self.assertEqual(shared_resources._NETWORK_POOLS[identity]["active"], 0)
            finally:
                shared_resources._NETWORK_POOLS[identity]["active"] = 0
                existing.close()

    def test_pool_shutdown_attempts_every_client_after_close_failure(self):
        close_network_resources()
        with shared_resources.network_client((None, None, None)) as first:
            pass
        with shared_resources.network_client(("http://other.test", None, None)) as second:
            pass
        try:
            with patch.object(first, "close", side_effect=ValueError("Close failed")):
                with self.assertRaises(ValueError):
                    close_network_resources()
            self.assertTrue(second.is_closed)
        finally:
            first.close()
            second.close()

    def test_index_eviction_releases_weak_client_reference(self):
        PARQUET_INDEXES.clear()
        payload = b"PAR1" + b"x" * 100 + FAKE_FOOTER_BYTES
        remote = FakeRangeClient(len(payload), payload=payload)
        with tempfile.TemporaryDirectory() as directory, patch.object(PARQUET_INDEXES, "max_entries", 1):
            fs = DatasetCacheFileSystem(directory=directory, version="weak-index-v1", http_client=remote,
                                        resolve=lambda url, refresh=False: (SIGNED, len(payload)))
            try:
                path = fs.register(PINNED)
                index = fs.shared_parquet_index(path, b"first", lambda: [(0, "symbol", "A", "Z", 4, 1)])
                owner = WeakValueDictionary({path: index})
                weak = ref(index)
                del index
                fs.shared_parquet_index(path, b"second", lambda: [(1, "symbol", "A", "Z", 4, 1)])
                gc.collect()
                self.assertIsNone(weak())
                self.assertNotIn(path, owner)
            finally:
                fs.close()
                PARQUET_INDEXES.clear()

    def test_spawned_processes_prepare_footer_once_and_restart_reuses_disk(self):
        payload = b"PAR1" + b"x" * 100 + FAKE_FOOTER_BYTES
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as directory, local_range_server(payload, delay_seconds=0.1) as server:
            url = f"https://127.0.0.1:{server.server_port}/file"
            start, messages = context.Event(), context.Queue()
            processes = [context.Process(target=shared_footer_process,
                                         args=(directory, url, len(payload), start, messages)) for _ in range(2)]
            try:
                for process in processes:
                    process.start()
                self.assertEqual([messages.get(timeout=30)[0] for _ in processes], ["ready", "ready"])
                start.set()
                results = [messages.get(timeout=30) for _ in processes]
                self.assertEqual(results, [("result", (4, FAKE_FOOTER_BYTES))] * 2)
                for process in processes:
                    process.join(timeout=15)
                    self.assertEqual(process.exitcode, 0)
                footer = next(Path(directory).glob("*.footer"))
                timestamp = footer.stat().st_mtime_ns
                restarted = context.Process(target=shared_footer_process,
                                            args=(directory, url, len(payload), start, messages))
                processes.append(restarted)
                restarted.start()
                self.assertEqual(messages.get(timeout=30)[0], "ready")
                self.assertEqual(messages.get(timeout=30), ("result", (4, FAKE_FOOTER_BYTES)))
                restarted.join(timeout=15)
                self.assertEqual(restarted.exitcode, 0)
                self.assertEqual(len(server.paths), 1)
                self.assertEqual(footer.stat().st_mtime_ns, timestamp)
            finally:
                start.set()
                for process in processes:
                    if process.is_alive():
                        process.terminate()
                    process.join(timeout=5)
                messages.close()
                messages.join_thread()

    def test_metadata_and_ranges_share_transport_and_owner_close_is_local(self):
        close_network_resources()
        observed = []

        def respond(request):
            observed.append((request.method, request.url.path))
            return httpx.Response(200, json={"ok": True})

        with httpx.Client(transport=httpx.MockTransport(respond)) as raw:
            with patch("defeatbeta_api.client.shared_resources.httpx.Client", return_value=raw) as create:
                first = SharedHttpClient(proxy="")
                second = SharedHttpClient(proxy="")
                metadata = MetadataSession()
                first.get("https://example.test/a")
                metadata.head("https://example.test/b", proxies={"https": None})
                first.close()
                metadata.close()
                second.get("https://example.test/c")
                self.assertEqual(create.call_count, 1)
                self.assertFalse(raw.is_closed)
        self.assertEqual(observed, [("GET", "/a"), ("HEAD", "/b"), ("GET", "/c")])

    def test_metadata_protocol_rejection_is_immediate_and_explains_h2_requirement(self):
        session = MetadataSession(max_retries=3)
        with patch.object(SharedHttpClient, "request", side_effect=httpx.UnsupportedProtocol(
                "HTTP/2 is required; TLS ALPN did not negotiate h2")) as request, \
                patch("defeatbeta_api.client.hf_session.time.sleep") as sleep:
            with self.assertRaisesRegex(requests.RequestException, "HTTPS.*HTTP/2"):
                session.get("https://example.test/spec.json")
        self.assertEqual(request.call_count, 1)
        sleep.assert_not_called()

    def test_single_flight_failure_releases_waiters_and_allows_retry(self):
        cache = SharedCache()
        entered, release = Event(), Event()
        calls = []

        def fail():
            calls.append(1)
            entered.set()
            release.wait(3)
            raise ValueError("Failed preparation")

        with ThreadPoolExecutor(max_workers=8) as executor:
            owner = executor.submit(cache.get_or_build, "file", fail)
            self.assertTrue(entered.wait(1))
            waiters = [executor.submit(cache.get_or_build, "file", fail) for _ in range(7)]
            time.sleep(0.03)
            release.set()
            for future in [owner, *waiters]:
                with self.assertRaises(ValueError):
                    future.result(timeout=3)
        self.assertEqual(len(calls), 1)
        self.assertEqual(cache.get_or_build("file", lambda: b"ok"), b"ok")

    def test_unrelated_files_prepare_concurrently_and_cache_is_bounded(self):
        cache = SharedCache(max_bytes=4, max_entries=2)
        entered, release = Event(), Event()

        def slow():
            entered.set()
            release.wait(3)
            return b"abc"

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(cache.get_or_build, "a", slow, weight=len)
            self.assertTrue(entered.wait(1))
            self.assertEqual(cache.get_or_build("b", lambda: b"xyz", weight=len), b"xyz")
            release.set()
            first.result(timeout=3)
        self.assertLessEqual(cache.bytes, 4)
        self.assertEqual(len(cache.values), 1)

    def test_network_identity_separates_proxy_and_tracks_environment_changes(self):
        with patch("defeatbeta_api.client.shared_resources.getproxies", return_value={
                "https": "http://proxy-one.test"}), patch(
                    "defeatbeta_api.client.shared_resources.proxy_bypass", return_value=False):
            self.assertEqual(network_identity("https://cdn.test/file")[0], "http://proxy-one.test")
            self.assertIsNone(network_identity("https://cdn.test/file", "")[0])
        self.assertNotEqual(network_identity("https://cdn.test/a", "http://one.test"),
                            network_identity("https://cdn.test/b", "http://two.test"))

    def test_independent_filesystems_share_one_footer_and_parsed_index(self):
        payload = b"PAR1" + b"x" * 100 + FAKE_FOOTER_BYTES
        remote = FakeRangeClient(len(payload), payload=payload)
        with tempfile.TemporaryDirectory() as directory:
            filesystems = [DatasetCacheFileSystem(
                directory=directory, version="shared-v1", http_client=remote,
                resolve=lambda url, refresh=False: (SIGNED, len(payload))) for _ in range(8)]
            try:
                paths = [fs.register(PINNED) for fs in filesystems]
                with ThreadPoolExecutor(max_workers=8) as executor:
                    sizes = list(executor.map(lambda pair: pair[0].prepare_footer(pair[1]),
                                              zip(filesystems, paths)))
                self.assertEqual(sizes, [4] * 8)
                self.assertEqual(len(remote.calls), 1)
                parses = []

                def parse():
                    parses.append(1)
                    time.sleep(0.02)
                    return [(0, "symbol", "A", "Z", 4, 100)]

                with ThreadPoolExecutor(max_workers=8) as executor:
                    results = list(executor.map(
                        lambda pair: pair[0].shared_parquet_index(
                            pair[1], pair[0].cached_footer_bytes(pair[1]), parse),
                        zip(filesystems, paths)))
                self.assertEqual(len(parses), 1)
                self.assertTrue(all(value is results[0] for value in results))
                footer = next(Path(directory).glob("*.footer"))
                timestamp = footer.stat().st_mtime_ns
                filesystems[0].close()
                filesystems[1].prepare_footer(paths[1])
                self.assertEqual(footer.stat().st_mtime_ns, timestamp)
            finally:
                for fs in filesystems:
                    fs.close()

    def test_shared_refresh_uses_generation_not_url_equality(self):
        cache = SharedCache()
        first = cache.get_or_build("file", lambda: ("same-url", 1))
        calls = []

        def refresh():
            calls.append(1)
            return "same-url", 2

        for _ in range(8):
            self.assertEqual(cache.get_or_build("file", refresh, force_if=first), ("same-url", 2))
        self.assertEqual(len(calls), 1)

    def test_http2_files_and_owners_reuse_verified_tls_connection(self):
        with http2_peer() as (url, certificate, server), patch.dict(
                os.environ, {"SSL_CERT_FILE": str(certificate)}):
            first, second = SharedHttpClient(proxy=""), SharedHttpClient(proxy="")
            self.assertEqual(first.get(url).http_version, "HTTP/2")
            first.close()
            self.assertEqual(second.get(url + "-other").content, b"x")
            self.assertEqual(server.connections, 1)
            self.assertEqual(server.streams, [(1, 1), (1, 3)])
            close_network_resources()

    def test_idle_goaway_is_recovered_on_demand_without_background_requests(self):
        with http2_peer(idle_retirement=0.1) as (url, certificate, server), patch.dict(
                os.environ, {"SSL_CERT_FILE": str(certificate)}):
            with tempfile.TemporaryDirectory() as directory:
                fs = DatasetCacheFileSystem(directory=directory, version="goaway-v1",
                                            resolve=lambda url_, refresh=False: (url, 100),
                                            http_proxy="", timeout=2)
                # Trust the fixture CA while retaining the explicit direct route.
                fs._clients[0].trust_env = True
                try:
                    self.assertEqual(fs._request_range(PINNED, 0, 0)[0], b"x")
                    time.sleep(0.25)
                    self.assertEqual(server.connections, 1)
                    self.assertEqual(server.streams, [(1, 1)])
                    self.assertEqual(fs._request_range(PINNED, 0, 0)[0], b"x")
                    self.assertEqual(server.connections, 2)
                finally:
                    fs.close()
                    close_network_resources()

    def test_concurrent_range_requests_recover_from_goaway(self):
        with http2_peer(retire_first=True) as (url, certificate, server), patch.dict(
                os.environ, {"SSL_CERT_FILE": str(certificate)}):
            with tempfile.TemporaryDirectory() as directory:
                fs = DatasetCacheFileSystem(directory=directory, version="goaway-v1",
                                            resolve=lambda url_, refresh=False: (url, 100),
                                            http_proxy="", timeout=2)
                fs._clients[0].trust_env = True
                try:
                    with ThreadPoolExecutor(max_workers=8) as executor:
                        results = list(executor.map(
                            lambda _: fs._request_range(PINNED, 0, 0)[0], range(8)))
                    self.assertEqual(results, [b"x"] * 8)
                    # One retired connection plus the configured healthy core.
                    self.assertGreaterEqual(server.connections, 2)
                    self.assertLessEqual(server.connections, 1 + get_connection_pool_status()[
                        "configuration"]["core_connections_per_origin"])
                finally:
                    fs.close()
                    close_network_resources()

    def test_disabled_cache_uses_shared_transport_without_disk_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "absent"
            remote = FakeRangeClient(100)
            fs = DatasetCacheFileSystem(
                directory=str(cache), version="network-v1", cache_enabled=False,
                resolve=lambda url, refresh=False: (SIGNED, 100), http_client=remote)
            try:
                path = fs.register(PINNED)
                fs.cat_file(path, 0, 1)
                fs.cat_file(path, 0, 1)
                self.assertEqual(len(remote.calls), 2)
                self.assertFalse(cache.exists())
            finally:
                fs.close()

    def test_footer_and_index_share_across_cache_directories(self):
        payload = b"PAR1" + b"x" * 100 + FAKE_FOOTER_BYTES
        remote = FakeRangeClient(len(payload), payload=payload)
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            filesystems = [DatasetCacheFileSystem(
                directory=root, version="cross-directory-v1", http_client=remote,
                resolve=lambda url, refresh=False: (SIGNED, len(payload))) for root in (first, second)]
            try:
                values = []
                for fs in filesystems:
                    path = fs.register(PINNED)
                    fs.prepare_footer(path)
                    self.assertEqual(len(list(fs.directory.glob("*.footer"))), 1)
                    values.append(fs.shared_parquet_index(path, fs.cached_footer_bytes(path),
                                                          lambda: [(0, "symbol", "A", "Z", 4, 1)]))
                self.assertEqual(len(remote.calls), 1)
                self.assertIs(values[0], values[1])
            finally:
                for fs in filesystems:
                    fs.close()

    def test_changed_footer_hint_cannot_reuse_unmatching_cached_footer(self):
        payload = b"PAR1" + b"x" * 100 + FAKE_FOOTER_BYTES
        remote = FakeRangeClient(len(payload), payload=payload)
        hint = {"file_size": len(payload), "footer_size": 4,
                "footer_sha256": hashlib.sha256(b"meta").hexdigest()}
        with tempfile.TemporaryDirectory() as directory:
            fs = DatasetCacheFileSystem(directory=directory, version="hint-v1", http_client=remote,
                                        resolve=lambda url, refresh=False: (SIGNED, len(payload)),
                                        footer_index={"US/stock_prices.parquet": hint})
            try:
                path = fs.register(PINNED)
                fs.prepare_footer(path)
                fs.update_version("hint-v1", footer_index={
                    "US/stock_prices.parquet": {**hint, "footer_sha256": "a" * 64}})
                with self.assertRaises(DatasetVersionChanged):
                    fs.prepare_footer(path)
                with self.assertRaisesRegex(ValueError, "spec.json"):
                    fs.prepare_footer(fs.register(PINNED))
            finally:
                fs.close()

    def test_real_duckdb_uncached_and_cache_failure_stay_on_project_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.parquet"
            connection = duckdb.connect()
            connection.execute("COPY (SELECT 'AAPL' AS symbol, 123 AS price) TO ? (FORMAT PARQUET)",
                               [str(source)])
            connection.close()
            payload = source.read_bytes()
            for enabled in (False, True):
                remote = FakeRangeClient(len(payload), payload=payload)
                root = Path(directory) / str(enabled)
                with patch.object(HuggingFaceClient, "get_shared_data_update_time", return_value="query-v1"), \
                        patch.object(HuggingFaceClient, "resolve_cdn_info", return_value=(SIGNED, len(payload))), \
                        patch.object(DatasetCacheFileSystem, "_new_clients", return_value=[remote]):
                    client = DuckDBClient(config=Configuration(
                        cache_enabled=enabled, cache_directory=str(root)), log_level=50)
                    try:
                        if enabled:
                            client._dataset_fs.cat_file = lambda *args, **kwargs: (
                                (_ for _ in ()).throw(OSError("Failed cache read")))
                        result = client.query(f"SELECT * FROM '{PINNED}'")
                        self.assertEqual(result.to_records(index=False).tolist(), [("AAPL", 123)])
                        self.assertIsNotNone(client._uncached_fs)
                        self.assertTrue(remote.calls)
                        if not enabled:
                            self.assertFalse(root.exists())
                    finally:
                        client.close()
