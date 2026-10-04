"""Tests for bounded, demand-driven dataset block caching."""

import tempfile
import threading
import unittest
import hashlib
import os
import time
import httpx
from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from unittest.mock import Mock, patch

import duckdb

from defeatbeta_api.client.dataset_cache_fs import DatasetCacheFileSystem
from defeatbeta_api.client.duckdb_client import DuckDBClient, plan_symbol_column_chunks
from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.data.ticker import Ticker


MIB = 1024 * 1024
FAKE_FOOTER_BYTES = b"meta" + (4).to_bytes(4, "little") + b"PAR1"
PINNED = (
    "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data"
    "/resolve/main/data/US/stock_prices.parquet"
)
SIGNED = "https://example.test/object?Signature=secret"
CATALOG = (
    "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data"
    "/resolve/main/data/US/company_tickers.json"
)
PROFILE = PINNED.replace("stock_prices.parquet", "stock_profile.parquet")


class FakeRangeClient:
    def __init__(self, size, payload=None, corrupt=False):
        self.size = size
        self.payload = payload
        self.corrupt = corrupt
        self.calls = []
        self.lock = threading.Lock()

    def get(self, url, headers):
        start, end = (
            int(part) for part in headers["Range"].removeprefix("bytes=").split("-")
        )
        with self.lock:
            self.calls.append((url, start, end))
        content = (
            self.payload[start:end + 1]
            if self.payload is not None else bytes([start // MIB % 256]) * (end - start + 1)
        )
        actual_start = start + int(self.corrupt and start > 0)
        return SimpleNamespace(
            status_code=206,
            headers={"Content-Range": f"bytes {actual_start}-{end}/{self.size}"},
            content=content,
            http_version="HTTP/2",
        )

    def close(self):
        pass


class TestDatasetCacheFileSystem(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.remote = FakeRangeClient(466_437_904)
        self.resolutions = []
        self.filesystem = DatasetCacheFileSystem(
            directory=self.temporary.name,
            version="dataset-v1",
            resolve=self._resolve,
            http_client=self.remote,
            max_disk_bytes=16 * MIB,
            workers=3,
        )

    def tearDown(self):
        self.filesystem.close()
        self.temporary.cleanup()

    def _resolve(self, url, refresh=False):
        self.resolutions.append((url, refresh))
        return SIGNED

    def test_spec_file_size_needs_no_resolve_or_size_file(self):
        resolve = Mock(side_effect=AssertionError("size must come from spec"))
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "spec-size"),
            version="dataset-v1", resolve=resolve, http_client=self.remote,
            max_disk_bytes=16 * MIB,
            footer_index={"US/stock_prices.parquet": {"file_size": self.remote.size}},
        )
        try:
            path = filesystem.register(PINNED)
            self.assertEqual(filesystem.info(path)["size"], self.remote.size)
            resolve.assert_not_called()
            self.assertFalse(list(filesystem.directory.glob("*-size.json")))
        finally:
            filesystem.close()

    def test_missing_spec_size_falls_back_without_persisting_size_file(self):
        path = self.filesystem.register(PINNED)
        self.assertEqual(self.filesystem.info(path)["size"], self.remote.size)
        self.assertEqual(len(self.remote.calls), 1)
        self.assertFalse(list(Path(self.temporary.name).glob("*-size.json")))

    def test_same_version_spec_refresh_replaces_in_memory_size(self):
        self.filesystem.update_version(
            "dataset-v1", footer_index={"US/stock_prices.parquet": {"file_size": 100}},
        )
        path = self.filesystem.register(PINNED)
        self.assertEqual(self.filesystem.info(path)["size"], 100)
        self.filesystem.update_version(
            "dataset-v1", footer_index={"US/stock_prices.parquet": {"file_size": 200}},
        )
        self.assertEqual(self.filesystem.info(path)["size"], 200)

    def test_rejects_disk_limit_smaller_than_one_data_byte(self):
        with self.assertRaisesRegex(ValueError, "one data byte"):
            DatasetCacheFileSystem(
                directory=self.temporary.name,
                version="dataset-v1",
                resolve=self._resolve,
                max_disk_bytes=hashlib.sha256().digest_size,
                http_client=self.remote,
            )

    def test_disk_limit_does_not_depend_on_memory_budget(self):
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "small-disk-limit"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, self.remote.size),
            http_client=self.remote,
            max_disk_bytes=10 + hashlib.sha256().digest_size,
            max_memory_bytes=64 * MIB,
        )
        try:
            path = filesystem.register(PINNED)
            self.assertEqual(filesystem.cat_file(path, 0, 10), b"\0" * 10)
        finally:
            filesystem.close()

    def test_unaligned_small_and_large_ranges_are_cached_exactly(self):
        self.filesystem.resolve = lambda url, refresh=False: (SIGNED, self.remote.size)
        path = self.filesystem.register(PINNED)
        start = MIB - 31
        length = MIB + 77
        self.filesystem.cat_file(path, 123, 160)
        self.filesystem.cat_file(path, start, start + length)

        self.assertEqual(
            [call[1:] for call in self.remote.calls],
            [(123, 159), (start, start + length - 1)],
        )
        key, _ = self.filesystem._key_and_url(path)
        self.assertTrue(self.filesystem._block_path(key, 123, 37).exists())
        self.assertTrue(self.filesystem._block_path(key, start, length).exists())

    def test_buffered_file_read_does_not_expand_to_an_internal_block(self):
        self.filesystem.resolve = lambda url, refresh=False: (SIGNED, self.remote.size)
        path = self.filesystem.register(PINNED)
        with self.filesystem.open(path, "rb") as stream:
            stream.seek(MIB - 3)
            self.assertEqual(stream.read(7), b"\0" * 7)
        self.assertEqual([call[1:] for call in self.remote.calls], [(MIB - 3, MIB + 3)])

    def test_cache_layout_selection_is_not_available(self):
        with self.assertRaisesRegex(TypeError, "cache_layout"):
            DatasetCacheFileSystem(
                directory=self.temporary.name, version="dataset-v1",
                resolve=self._resolve, http_client=self.remote,
                cache_layout="block",
            )

    def test_large_file_fetches_only_demanded_extents_and_reuses_them(self):
        path = self.filesystem.register(PINNED)
        self.assertEqual(self.filesystem.cat_file(path, 10, 20), b"\0" * 10)
        tail = self.remote.size - 50
        self.assertEqual(len(self.filesystem.cat_file(path, tail, tail + 10)), 10)
        self.assertEqual(len(self.remote.calls), 3)
        self.assertEqual(sum(end - start + 1 for _, start, end in self.remote.calls),
                         1 + 10 + 10)

        self.filesystem.cat_file(path, 10, 20)
        self.filesystem.cat_file(path, tail, tail + 10)
        self.assertEqual(len(self.remote.calls), 3)
        self.assertEqual(len(self.resolutions), 4)
        self.assertNotIn("Signature", " ".join(
            str(item) for item in Path(self.temporary.name).rglob("*")
        ))
        self.assertEqual(
            {event["file"] for event in self.filesystem.range_events()},
            {"stock_prices.parquet"},
        )

    def test_io_cache_downloads_only_missing_byte_intervals(self):
        payload = bytes(range(256)) * (4 * MIB // 256)
        remote = FakeRangeClient(len(payload), payload=payload)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "io-intervals"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote,
            max_disk_bytes=16 * MIB,
        )
        try:
            self.assertFalse(hasattr(filesystem, "cache_layout"))
            path = filesystem.register(PINNED)
            self.assertEqual(filesystem.cat_file(path, 100, 200), payload[100:200])
            self.assertEqual(filesystem.cat_file(path, 150, 250), payload[150:250])
            self.assertEqual(filesystem.cat_file(path, 120, 240), payload[120:240])
            self.assertEqual([call[1:] for call in remote.calls], [(100, 199), (200, 249)])
            self.assertEqual(filesystem.metrics()["downloaded_bytes"], 150)
        finally:
            filesystem.close()

    def test_io_cache_reuses_variable_extents_after_restart(self):
        payload = bytes(range(256)) * (4 * MIB // 256)
        directory = str(Path(self.temporary.name) / "io-restart")
        remote = FakeRangeClient(len(payload), payload=payload)
        settings = dict(
            directory=directory, version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote,
            max_disk_bytes=16 * MIB,
        )
        first = DatasetCacheFileSystem(**settings)
        try:
            path = first.register(PINNED)
            first.cat_file(path, 10, 20)
            first.cat_file(path, 20, 30)
        finally:
            first.close()
        second = DatasetCacheFileSystem(**settings)
        try:
            path = second.register(PINNED)
            self.assertEqual(second.cat_file(path, 12, 28), payload[12:28])
            self.assertEqual([call[1:] for call in remote.calls], [(10, 19), (20, 29)])
        finally:
            second.close()

    def test_io_cache_concurrent_readers_share_one_exact_range(self):
        remote = FakeRangeClient(4 * MIB)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "io-concurrent"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, 4 * MIB),
            http_client=remote,
            max_disk_bytes=16 * MIB,
        )
        try:
            path = filesystem.register(PINNED)
            with ThreadPoolExecutor(max_workers=10) as readers:
                results = list(readers.map(
                    lambda _: filesystem.cat_file(path, 100, 200), range(10)
                ))
            self.assertEqual(results, [b"\0" * 100] * 10)
            self.assertEqual([call[1:] for call in remote.calls], [(100, 199)])
        finally:
            filesystem.close()

    def test_io_cache_rejects_corruption_and_keeps_version_isolation(self):
        payload = bytes(range(256)) * (MIB // 256)
        remote = FakeRangeClient(len(payload), payload=payload)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "io-version"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote,
            max_disk_bytes=16 * MIB, max_memory_bytes=0,
        )
        try:
            path = filesystem.register(PINNED)
            filesystem.cat_file(path, 100, 200)
            block = next(Path(filesystem.directory).glob("*.block"))
            block.write_bytes(b"x" * block.stat().st_size)
            self.assertEqual(filesystem.cat_file(path, 100, 200), payload[100:200])
            self.assertEqual(len(remote.calls), 2)
            filesystem.update_version("dataset-v2")
            path = filesystem.register(PINNED)
            self.assertEqual(filesystem.cat_file(path, 100, 200), payload[100:200])
            self.assertEqual(len(remote.calls), 3)
        finally:
            filesystem.close()

    def test_io_cache_records_reader_ranges_without_signed_urls(self):
        remote = FakeRangeClient(4 * MIB)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "io-observations"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, 4 * MIB),
            http_client=remote,
            max_disk_bytes=16 * MIB,
        )
        try:
            path = filesystem.register(PINNED)
            previous = filesystem.read_event_sequence()
            filesystem.cat_file(path, 100, 200)
            self.assertEqual(filesystem.read_events(previous), [{
                "sequence": previous + 1,
                "file": "stock_prices.parquet",
                "object_id": hashlib.sha256(PINNED.encode()).hexdigest(),
                "start": 100,
                "end": 200,
                "bytes": 100,
            }])
            self.assertNotIn("Signature", str(filesystem.read_events(previous)))
        finally:
            filesystem.close()

    def test_same_named_files_have_distinct_event_identities(self):
        first = self.filesystem.register(PINNED)
        second = self.filesystem.register(PINNED.replace("/US/", "/EU/"))
        self.filesystem.cat_file(first, 100, 101)
        self.filesystem.cat_file(second, 100, 101)
        object_ids = {event["object_id"] for event in self.filesystem.read_events()}
        self.assertEqual(len(object_ids), 2)
        self.assertEqual(
            {event["object_id"] for event in self.filesystem.range_events()
             if event["start"] == 100},
            object_ids,
        )

    def test_event_capture_reports_bounded_buffer_overflow(self):
        self.filesystem.resolve = lambda url, refresh=False: (SIGNED, self.remote.size)
        range_start = self.filesystem.range_event_sequence()
        for start in range(1025):
            self.filesystem._request_range(PINNED, start, start, self.remote.size)
        self.assertEqual(len(self.filesystem.range_events(range_start)), 1024)
        self.assertFalse(self.filesystem.range_events_complete(range_start))

        path = self.filesystem.register(PINNED)
        read_start = self.filesystem.read_event_sequence()
        for _ in range(4097):
            self.filesystem.cat_file(path, 1025, 1026)
        self.assertEqual(len(self.filesystem.read_events(read_start)), 4096)
        self.assertFalse(self.filesystem.read_events_complete(read_start))

    def test_io_cache_prefetches_unaligned_ranges_concurrently(self):
        payload = bytes(range(256)) * (4 * MIB // 256)
        gate = threading.Barrier(2, timeout=3)

        class ConcurrentClient(FakeRangeClient):
            def get(self, url, headers):
                gate.wait()
                return super().get(url, headers)

        remote = ConcurrentClient(len(payload), payload=payload)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "io-prefetch"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote,
            max_disk_bytes=16 * MIB, workers=2,
        )
        try:
            path = filesystem.register(PINNED)
            filesystem.prefetch_ranges(path, [(100, 200), (1000, 1100)])
            self.assertEqual(filesystem.cat_file(path, 125, 175), payload[125:175])
            self.assertEqual(filesystem.cat_file(path, 1025, 1075), payload[1025:1075])
            self.assertEqual(sorted(call[1:] for call in remote.calls),
                             [(100, 199), (1000, 1099)])
        finally:
            filesystem.close()

    def test_pending_prefetch_can_be_drained_after_query_timing(self):
        payload = bytes(range(256)) * (MIB // 256)
        started = threading.Event()
        release = threading.Event()

        class DelayedClient(FakeRangeClient):
            def get(self, url, headers):
                started.set()
                if not release.wait(timeout=3):
                    raise TimeoutError("Prefetch was not released")
                return super().get(url, headers)

        remote = DelayedClient(len(payload), payload=payload)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "pending-prefetch"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote,
            max_disk_bytes=16 * MIB,
        )
        try:
            path = filesystem.register(PINNED)
            filesystem.prefetch_ranges(path, [(100, 200)])
            self.assertTrue(started.wait(timeout=2))
            self.assertEqual(filesystem.metrics()["downloaded_bytes"], 0)
            release.set()
            self.assertEqual(filesystem.await_pending()["errors"], 0)
            self.assertEqual(filesystem.metrics()["downloaded_bytes"], 100)
        finally:
            release.set()
            filesystem.close()

    def test_failed_async_prefetch_does_not_poison_demand_read(self):
        class RecoveringClient(FakeRangeClient):
            def get(self, url, headers):
                if len(self.calls) < 2:
                    self.calls.append((url, headers["Range"]))
                    raise httpx.ConnectError("proxy disconnected")
                return super().get(url, headers)

        remote = RecoveringClient(4 * MIB)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "failed-prefetch"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, remote.size),
            http_client=remote,
            max_disk_bytes=16 * MIB,
        )
        try:
            path = filesystem.register(PINNED)
            filesystem.prefetch_ranges(path, [(100, 200)])
            filesystem.await_pending()
            self.assertEqual(filesystem.metrics()["downloaded_bytes"], 0)
            self.assertEqual(filesystem.cat_file(path, 100, 200), b"\0" * 100)
            self.assertEqual(filesystem.metrics()["downloaded_bytes"], 100)
        finally:
            filesystem.close()

    def test_io_prefetch_reuses_prepared_footer_bytes(self):
        footer = b"m" * 4096
        payload = b"PAR1" + b"d" * 100_000 + footer + len(footer).to_bytes(4, "little") + b"PAR1"
        remote = FakeRangeClient(len(payload), payload=payload)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "prefetch-footer"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote,
            max_disk_bytes=16 * MIB,
        )
        try:
            path = filesystem.register(PINNED)
            filesystem.prepare_footer(path)
            filesystem.prefetch_ranges(path, [(4, 100)])
            self.assertEqual(filesystem.cat_file(path, 4, 100), payload[4:100])
            self.assertEqual([call[1:] for call in remote.calls], [(0, len(payload) - 1)])
        finally:
            filesystem.close()

    def test_footer_index_fetches_only_the_exact_footer(self):
        footer = b"footer metadata"
        payload = b"PAR1" + b"d" * MIB + footer + len(footer).to_bytes(4, "little") + b"PAR1"
        remote = FakeRangeClient(len(payload), payload=payload)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "exact-footer"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote, max_disk_bytes=16 * MIB,
            footer_index={"US/stock_prices.parquet": {
                "file_size": len(payload), "footer_size": len(footer),
                "footer_sha256": hashlib.sha256(footer).hexdigest(),
            }},
        )
        try:
            path = filesystem.register(PINNED)
            self.assertEqual(filesystem.prepare_footer(path), len(footer))
            self.assertEqual([call[1:] for call in remote.calls], [
                (len(payload) - len(footer) - 8, len(payload) - 1),
            ])
            self.assertEqual(filesystem.metrics()["downloaded_bytes"], len(footer) + 8)
        finally:
            filesystem.close()

    def test_footer_index_with_stale_size_rejects_remote_mismatch(self):
        footer = b"footer metadata"
        payload = b"PAR1" + b"d" * MIB + footer + len(footer).to_bytes(4, "little") + b"PAR1"
        remote = FakeRangeClient(len(payload), payload=payload)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "stale-footer-size"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote, max_disk_bytes=16 * MIB,
            footer_index={"US/stock_prices.parquet": {
                "file_size": len(payload) + 1, "footer_size": len(footer),
                "footer_sha256": hashlib.sha256(footer).hexdigest(),
            }},
        )
        try:
            path = filesystem.register(PINNED)
            with self.assertRaisesRegex(ValueError, "inconsistent range"):
                filesystem.prepare_footer(path)
            self.assertFalse(list(filesystem.directory.glob("*.footer")))
        finally:
            filesystem.close()

    def test_footer_index_hash_mismatch_is_not_published(self):
        footer = b"footer metadata"
        payload = b"PAR1" + b"d" * MIB + footer + len(footer).to_bytes(4, "little") + b"PAR1"
        remote = FakeRangeClient(len(payload), payload=payload)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "stale-footer-hash"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote, max_disk_bytes=16 * MIB,
            footer_index={"US/stock_prices.parquet": {
                "file_size": len(payload), "footer_size": len(footer),
                "footer_sha256": "0" * 64,
            }},
        )
        try:
            with self.assertRaisesRegex(ValueError, "does not match spec.json"):
                filesystem.prepare_footer(filesystem.register(PINNED))
            self.assertFalse(list(filesystem.directory.glob("*.footer")))
        finally:
            filesystem.close()

    def test_version_update_discards_old_footer_index(self):
        footer = b"footer metadata"
        payload = b"PAR1" + b"d" * MIB + footer + len(footer).to_bytes(4, "little") + b"PAR1"
        remote = FakeRangeClient(len(payload), payload=payload)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "footer-version-index"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote, max_disk_bytes=16 * MIB,
            footer_index={"US/stock_prices.parquet": {
                "file_size": len(payload), "footer_size": len(footer),
                "footer_sha256": hashlib.sha256(footer).hexdigest(),
            }},
        )
        try:
            filesystem.prepare_footer(filesystem.register(PINNED))
            filesystem.update_version("dataset-v2")
            filesystem.prepare_footer(filesystem.register(PINNED))
            self.assertEqual(len(remote.calls), 2)
            self.assertEqual(remote.calls[1][1], len(payload) - 256 * 1024)
        finally:
            filesystem.close()

    def test_io_prefetch_downloads_only_uncovered_suffix(self):
        payload = bytes(range(256)) * (4 * MIB // 256)
        remote = FakeRangeClient(len(payload), payload=payload)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "prefetch-overlap"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote,
            max_disk_bytes=16 * MIB,
        )
        try:
            path = filesystem.register(PINNED)
            filesystem.cat_file(path, 100, 200)
            filesystem.prefetch_ranges(path, [(150, 250)])
            self.assertEqual(filesystem.cat_file(path, 150, 250), payload[150:250])
            self.assertEqual([call[1:] for call in remote.calls], [(100, 199), (200, 249)])
        finally:
            filesystem.close()

    def test_io_prefetch_reuses_overlapping_in_flight_ranges(self):
        payload = bytes(range(256)) * (4 * MIB // 256)
        remote = FakeRangeClient(len(payload), payload=payload)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "prefetch-pending-overlap"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote,
            max_disk_bytes=16 * MIB, workers=2,
        )
        try:
            path = filesystem.register(PINNED)
            filesystem.prefetch_ranges(path, [(100, 200), (150, 250)])
            self.assertEqual(filesystem.cat_file(path, 100, 250), payload[100:250])
            self.assertEqual(sorted(call[1:] for call in remote.calls),
                             [(100, 199), (200, 249)])
        finally:
            filesystem.close()

    def test_footer_warmup_persists_validated_bytes_across_restart(self):
        footer = b"m" * (300 * 1024)
        payload = (b"PAR1" + b"d" * MIB + footer
                   + len(footer).to_bytes(4, "little") + b"PAR1")
        remote = FakeRangeClient(len(payload), payload=payload)
        directory = str(Path(self.temporary.name) / "footer-warmup")
        settings = dict(
            directory=directory, version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote,
            max_disk_bytes=16 * MIB,
        )
        first = DatasetCacheFileSystem(**settings)
        try:
            path = first.register(PINNED)
            self.assertEqual(first.prepare_footer(path), len(footer))
            self.assertEqual(first.cat_file(path, len(payload) - 100, len(payload)),
                             payload[-100:])
            self.assertEqual(len(remote.calls), 2)
            self.assertEqual(len(list(Path(directory).glob("*.footer"))), 1)
            self.assertEqual(len(list(Path(directory).glob("*.block"))), 0)
            self.assertFalse(list(Path(directory).glob("*-index.json")))
        finally:
            first.close()

        second = DatasetCacheFileSystem(**settings)
        try:
            path = second.register(PINNED)
            self.assertEqual(second.prepare_footer(path), len(footer))
            self.assertEqual(second.cat_file(path, len(payload) - 100, len(payload)),
                             payload[-100:])
            self.assertEqual(len(remote.calls), 2)
        finally:
            second.close()

    def test_parquet_metadata_after_restart_uses_only_cached_footer(self):
        source = Path(self.temporary.name) / "source.parquet"
        writer = duckdb.connect(":memory:")
        try:
            writer.execute(
                "COPY (SELECT 'AAPL' AS symbol, range AS price FROM range(100)) "
                "TO ? (FORMAT PARQUET)", [str(source)],
            )
        finally:
            writer.close()
        payload = source.read_bytes()
        footer_size = int.from_bytes(payload[-8:-4], "little")
        footer = payload[-footer_size - 8:-8]
        remote = FakeRangeClient(len(payload), payload=payload)
        settings = dict(
            directory=str(Path(self.temporary.name) / "restart-footer"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote, max_disk_bytes=16 * MIB,
            footer_index={"US/stock_prices.parquet": {
                "file_size": len(payload), "footer_size": footer_size,
                "footer_sha256": hashlib.sha256(footer).hexdigest(),
            }},
        )
        first = DatasetCacheFileSystem(**settings)
        try:
            first.prepare_footer(first.register(PINNED))
            self.assertEqual(len(remote.calls), 1)
        finally:
            first.close()

        second = DatasetCacheFileSystem(**settings)
        self.assertIsNot(first, second)
        connection = duckdb.connect(":memory:")
        connection.register_filesystem(second)
        try:
            path = second.register(PINNED)
            client = DuckDBClient.__new__(DuckDBClient)
            client._dataset_fs = second
            client._parquet_indexes = {}
            client.connection = connection
            rows = client._load_or_build_parquet_index(PINNED, path)
            self.assertTrue(any(row[1] == "symbol" for row in rows))
            self.assertEqual(len(remote.calls), 1)
            self.assertFalse(list(second.directory.glob("*-index.json")))
            self.assertFalse(list(second.directory.glob("*-size.json")))
        finally:
            connection.close()
            second.close()

    def test_corrupt_cached_footer_is_downloaded_again_after_restart(self):
        footer = b"metadata"
        payload = b"PAR1" + b"d" * MIB + footer + len(footer).to_bytes(4, "little") + b"PAR1"
        remote = FakeRangeClient(len(payload), payload=payload)
        settings = dict(
            directory=str(Path(self.temporary.name) / "corrupt-restart-footer"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote, max_disk_bytes=16 * MIB,
            footer_index={"US/stock_prices.parquet": {
                "file_size": len(payload), "footer_size": len(footer),
                "footer_sha256": hashlib.sha256(footer).hexdigest(),
            }},
        )
        first = DatasetCacheFileSystem(**settings)
        try:
            first.prepare_footer(first.register(PINNED))
            cached = next(first.directory.glob("*.footer"))
            cached.write_bytes(b"broken")
        finally:
            first.close()
        second = DatasetCacheFileSystem(**settings)
        self.assertIsNot(first, second)
        try:
            path = second.register(PINNED)
            self.assertEqual(second.prepare_footer(path), len(footer))
            self.assertEqual(len(remote.calls), 2)
            self.assertEqual(second.cached_footer_bytes(path), payload[-len(footer) - 8:])
        finally:
            second.close()

    def test_large_price_footer_index_is_fetched_in_one_range(self):
        size = 468_390_307
        footer = b"m" * 294_000
        suffix = footer + len(footer).to_bytes(4, "little") + b"PAR1"

        class SparseParquetClient(FakeRangeClient):
            def get(self, url, headers):
                start, end = (
                    int(part) for part in headers["Range"].removeprefix("bytes=").split("-")
                )
                with self.lock:
                    self.calls.append((url, start, end))
                content = bytearray(b"d" * (end - start + 1))
                overlap = max(start, size - len(suffix))
                if overlap <= end:
                    content[overlap - start:] = suffix[
                        overlap - (size - len(suffix)):end - (size - len(suffix)) + 1
                    ]
                return SimpleNamespace(
                    status_code=206,
                    headers={"Content-Range": f"bytes {start}-{end}/{size}"},
                    content=bytes(content),
                    http_version="HTTP/2",
                )

        remote = SparseParquetClient(size)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "large-price-footer"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, size),
            http_client=remote,
            max_disk_bytes=16 * MIB,
            footer_index={"US/stock_prices.parquet": {
                "file_size": size, "footer_size": len(footer),
                "footer_sha256": hashlib.sha256(footer).hexdigest(),
            }},
        )
        try:
            path = filesystem.register(PINNED)
            self.assertEqual(filesystem.prepare_footer(path), len(footer))
            self.assertEqual(len(remote.calls), 1)
            self.assertLessEqual(filesystem.metrics()["downloaded_bytes"], 512 * 1024)
        finally:
            filesystem.close()

        remote.calls.clear()
        other = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "large-profile-footer"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, size),
            http_client=remote,
            max_disk_bytes=16 * MIB,
        )
        try:
            path = other.register(PROFILE)
            self.assertEqual(other.prepare_footer(path), len(footer))
            self.assertEqual(len(remote.calls), 2)
        finally:
            other.close()

    def test_invalid_footer_is_not_published(self):
        payload = b"d" * MIB + b"invalid!"
        remote = FakeRangeClient(len(payload), payload=payload)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "invalid-footer"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote,
            max_disk_bytes=16 * MIB,
        )
        try:
            with self.assertRaisesRegex(ValueError, "footer"):
                filesystem.prepare_footer(filesystem.register(PINNED))
            self.assertFalse(list(Path(filesystem.directory).glob("*.footer")))
        finally:
            filesystem.close()

    def test_prepared_footer_is_served_from_memory_without_disk_lookup(self):
        footer = b"m" * 4096
        payload = b"PAR1" + b"d" * MIB + footer + len(footer).to_bytes(4, "little") + b"PAR1"
        remote = FakeRangeClient(len(payload), payload=payload)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "memory-footer"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote,
            max_disk_bytes=16 * MIB,
        )
        try:
            path = filesystem.register(PINNED)
            filesystem.prepare_footer(path)
            footer_file = next(filesystem.directory.glob("*.footer"))
            footer_file.unlink()
            before = len(remote.calls)
            start = len(payload) - 100
            self.assertEqual(filesystem.cat_file(path, start, len(payload)), payload[start:])
            self.assertEqual(len(remote.calls), before)
            self.assertGreater(filesystem.metrics()["cache_hits"], 0)
        finally:
            filesystem.close()

    def test_obsolete_metadata_files_are_removed(self):
        footer = b"m" * 4096
        payload = b"PAR1" + b"d" * MIB + footer + len(footer).to_bytes(4, "little") + b"PAR1"
        remote = FakeRangeClient(len(payload), payload=payload)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "corrupt-index"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote,
            max_disk_bytes=16 * MIB,
        )
        try:
            path = filesystem.register(PINNED)
            filesystem.prepare_footer(path)
            key, _ = filesystem._key_and_url(path)
            prefix = filesystem._object_name(key)
            obsolete = [
                filesystem.directory / f"{prefix}-index.json",
                filesystem.directory / f"{prefix}-size.json",
            ]
            for item in obsolete:
                item.write_text("{}", encoding="utf-8")
            filesystem.cleanup_stale()
            self.assertTrue(all(not item.exists() for item in obsolete))
            self.assertEqual(len(list(filesystem.directory.glob("*.footer"))), 1)
        finally:
            filesystem.close()

    def test_footer_is_not_reused_after_version_change(self):
        footer = b"m" * 4096
        payload = b"PAR1" + b"d" * MIB + footer + len(footer).to_bytes(4, "little") + b"PAR1"
        remote = FakeRangeClient(len(payload), payload=payload)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "footer-version"),
            version="2026-09-28T00:00:00Z",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote,
            max_disk_bytes=16 * MIB,
        )
        try:
            old_path = filesystem.register(PINNED)
            filesystem.prepare_footer(old_path)
            filesystem.update_version("2026-09-29T00:00:00Z")
            new_path = filesystem.register(PINNED)
            self.assertFalse(list(filesystem.directory.glob("*.footer")))
            filesystem.prepare_footer(new_path)
            self.assertEqual(len(list(filesystem.directory.glob("*.footer"))), 1)
        finally:
            filesystem.close()

    def test_concurrent_footer_preparation_fetches_once(self):
        footer = b"m" * 4096
        payload = b"PAR1" + b"d" * MIB + footer + len(footer).to_bytes(4, "little") + b"PAR1"
        remote = FakeRangeClient(len(payload), payload=payload)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "concurrent-footer"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote,
            max_disk_bytes=16 * MIB,
        )
        try:
            path = filesystem.register(PINNED)
            with ThreadPoolExecutor(max_workers=8) as executor:
                sizes = list(executor.map(filesystem.prepare_footer, [path] * 8))
            self.assertEqual(sizes, [len(footer)] * 8)
            self.assertEqual(len(remote.calls), 1)
        finally:
            filesystem.close()

    def test_parquet_chunk_plan_selects_symbol_groups_and_merges_adjacent_columns(self):
        chunks = [
            (0, "symbol", "AAPL", "AAPL", 4, 100),
            (0, "price", None, None, 104, 200),
            (1, "symbol", "KDP", "MSFT", 304, 60),
            (1, "price", None, None, 364, 140),
            (2, "symbol", None, None, 504, 40),
            (2, "price", None, None, 544, 80),
        ]
        self.assertEqual(plan_symbol_column_chunks(chunks, "AAPL"),
                         [(4, 304), (504, 624)])
        self.assertEqual(plan_symbol_column_chunks(chunks, "KDP"),
                         [(304, 504), (504, 624)])
        self.assertEqual(plan_symbol_column_chunks(
            chunks, "AAPL", columns={"symbol"}),
            [(4, 104), (504, 544)],
        )

    def test_parquet_chunk_plan_rejects_incomplete_metadata(self):
        self.assertEqual(plan_symbol_column_chunks([], "AAPL"), [])
        self.assertEqual(plan_symbol_column_chunks(
            [(0, "price", None, None, 4, 100)], "AAPL"), [])

    def test_bad_range_does_not_publish_block(self):
        self.remote.corrupt = True
        path = self.filesystem.register(PINNED)
        with self.assertRaisesRegex(ValueError, "range"):
            self.filesystem.cat_file(path, MIB, MIB + 10)
        self.assertFalse(list(Path(self.temporary.name).rglob("*.block")))

    def test_same_length_disk_corruption_is_refetched(self):
        self.filesystem.max_memory_bytes = 0
        path = self.filesystem.register(PINNED)
        self.filesystem.cat_file(path, 0, 10)
        block = next(Path(self.temporary.name).rglob("*.block"))
        block.write_bytes(b"x" * block.stat().st_size)

        self.assertEqual(self.filesystem.cat_file(path, 0, 10), b"\0" * 10)
        self.assertEqual(len(self.remote.calls), 3)

    def test_disk_eviction_does_not_delete_unowned_block_files(self):
        self.filesystem.resolve = lambda url, refresh=False: (SIGNED, self.remote.size)
        self.filesystem.max_disk_bytes = 2 * (10 + hashlib.sha256().digest_size)
        foreign = Path(self.temporary.name) / "user-owned.block"
        foreign.write_bytes(b"unrelated" * 10)
        os.utime(foreign, ns=(1_000_000_000, 1_000_000_000))

        path = self.filesystem.register(PINNED)
        self.filesystem.cat_file(path, 0, 10)

        self.assertTrue(foreign.exists())

    def test_disk_eviction_keeps_recently_used_extents(self):
        self.filesystem.resolve = lambda url, refresh=False: (SIGNED, self.remote.size)
        self.filesystem.max_disk_bytes = 2 * (10 + hashlib.sha256().digest_size)
        path = self.filesystem.register(PINNED)
        self.filesystem.cat_file(path, 0, 10)
        self.filesystem.cat_file(path, 100, 110)
        key, _ = self.filesystem._key_and_url(path)
        first = self.filesystem._block_path(key, 0, 10)
        second = self.filesystem._block_path(key, 100, 10)
        third = self.filesystem._block_path(key, 200, 10)
        os.utime(first, ns=(1_000_000_000, 1_000_000_000))
        os.utime(second, ns=(2_000_000_000, 2_000_000_000))
        self.filesystem.cat_file(path, 0, 10)
        self.filesystem.cat_file(path, 200, 210)

        self.assertTrue(first.exists())
        self.assertFalse(second.exists())
        self.assertTrue(third.exists())
        self.assertLessEqual(
            sum(block.stat().st_size for block in Path(self.temporary.name).rglob("*.block")),
            self.filesystem.max_disk_bytes,
        )

    def test_disk_eviction_orders_accesses_with_equal_clock_ticks(self):
        self.filesystem.resolve = lambda url, refresh=False: (SIGNED, self.remote.size)
        self.filesystem.max_disk_bytes = 2 * (10 + hashlib.sha256().digest_size)
        path = self.filesystem.register(PINNED)
        key, _ = self.filesystem._key_and_url(path)
        first = self.filesystem._block_path(key, 0, 10)
        second = self.filesystem._block_path(key, 100, 10)
        third = self.filesystem._block_path(key, 200, 10)

        fixed_clock = time.time_ns() + 5_000_000_000
        with patch("defeatbeta_api.client.dataset_cache_fs.time.time_ns",
                   return_value=fixed_clock):
            self.filesystem.cat_file(path, 0, 10)
            self.filesystem.cat_file(path, 100, 110)
            self.filesystem.cat_file(path, 0, 10)
            self.filesystem.cat_file(path, 200, 210)

        self.assertTrue(first.exists())
        self.assertFalse(second.exists())
        self.assertTrue(third.exists())

    def test_disk_hit_refreshes_eviction_order_without_memory_cache(self):
        self.filesystem.resolve = lambda url, refresh=False: (SIGNED, self.remote.size)
        self.filesystem.max_memory_bytes = 0
        self.filesystem.max_disk_bytes = 2 * (10 + hashlib.sha256().digest_size)
        path = self.filesystem.register(PINNED)
        self.filesystem.cat_file(path, 0, 10)
        self.filesystem.cat_file(path, 100, 110)
        key, _ = self.filesystem._key_and_url(path)
        first = self.filesystem._block_path(key, 0, 10)
        second = self.filesystem._block_path(key, 100, 10)
        os.utime(first, ns=(1_000_000_000, 1_000_000_000))
        os.utime(second, ns=(2_000_000_000, 2_000_000_000))

        self.filesystem.cat_file(path, 0, 10)
        self.filesystem.cat_file(path, 200, 210)

        self.assertTrue(first.exists())
        self.assertFalse(second.exists())
        self.assertEqual(len(self.remote.calls), 3)

    def test_eviction_preserves_footer_metadata(self):
        payload = b"PAR1" + b"d" * (2 * MIB) + b"meta" + (4).to_bytes(4, "little") + b"PAR1"
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "eviction-metadata"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=FakeRangeClient(len(payload), payload=payload),
            max_disk_bytes=16 * MIB,
        )
        try:
            path = filesystem.register(PINNED)
            filesystem.prepare_footer(path)
            footer = next(filesystem.directory.glob("*.footer"))
            filesystem.max_disk_bytes = 2 * (10 + hashlib.sha256().digest_size)
            for start in (0, 100, 200):
                filesystem.cat_file(path, start, start + 10)
            self.assertEqual(len(list(filesystem.directory.glob("*.block"))), 2)
            self.assertTrue(footer.exists())
            self.assertFalse(list(filesystem.directory.glob("*-index.json")))
        finally:
            filesystem.close()

    def test_resolve_head_size_avoids_probe_range(self):
        self.filesystem.resolve = lambda url, refresh=False: (SIGNED, self.remote.size)
        path = self.filesystem.register(PINNED)
        self.filesystem.cat_file(path, 10, 20)
        self.assertEqual(len(self.remote.calls), 1)
        self.assertEqual(self.remote.calls[0][1:], (10, 19))

    def test_hot_block_is_served_without_another_disk_read(self):
        path = self.filesystem.register(PINNED)
        self.filesystem.cat_file(path, 10, 20)
        with patch.object(self.filesystem, "_read_block",
                          side_effect=AssertionError("hot block reread from disk")):
            self.assertEqual(self.filesystem.cat_file(path, 10, 20), b"\0" * 10)

    def test_memory_lru_respects_configured_byte_limit(self):
        self.filesystem.max_memory_bytes = 20
        path = self.filesystem.register(PINNED)
        for start in (0, MIB, 2 * MIB):
            self.filesystem.cat_file(path, start, start + 10)
        self.assertEqual(len(self.filesystem._memory_blocks), 2)

    def test_memory_tier_has_an_independent_extent_count_limit(self):
        self.filesystem.resolve = lambda url, refresh=False: (SIGNED, self.remote.size)
        path = self.filesystem.register(PINNED)
        for start in range(65):
            self.filesystem.cat_file(path, start * 2, start * 2 + 1)
        self.assertEqual(len(self.filesystem._memory_blocks), 64)

    def test_one_network_client_uses_configured_worker_capacity(self):
        self.assertEqual(self.filesystem._network_executor._max_workers, 3)

    def test_concurrent_readers_share_one_range_download(self):
        self.filesystem.resolve = lambda url, refresh=False: (SIGNED, self.remote.size)
        path = self.filesystem.register(PINNED)
        with ThreadPoolExecutor(max_workers=10) as readers:
            results = list(readers.map(
                lambda _: self.filesystem.cat_file(path, 0, 10), range(10)
            ))
        self.assertEqual(results, [b"\0" * 10] * 10)
        self.assertEqual(len(self.remote.calls), 1)

    def test_split_ranges_publish_one_validated_block_and_keep_hot_reads_local(self):
        payload = bytes(range(256)) * (MIB // 256)
        clients = [FakeRangeClient(MIB * 30, payload=payload * 30) for _ in range(2)]
        candidate_directory = Path(self.temporary.name) / "split-candidate"
        with patch("defeatbeta_api.client.dataset_cache_fs.httpx.Client",
                   side_effect=clients):
            filesystem = DatasetCacheFileSystem(
                directory=str(candidate_directory), version="dataset-v1",
                resolve=lambda url, refresh=False: (SIGNED, MIB * 30),
                max_disk_bytes=16 * MIB,
                network_connections=2, network_chunk_size=MIB // 2,
            )
        try:
            path = filesystem.register(PINNED)
            self.assertEqual(filesystem.cat_file(path, 0, MIB), payload)
            self.assertEqual(sorted(call[1:] for client in clients for call in client.calls),
                             [(0, MIB // 2 - 1), (MIB // 2, MIB - 1)])
            self.assertEqual(len(list(candidate_directory.glob("*.block"))), 1)
            filesystem.cat_file(path, 100, 200)
            self.assertEqual(sum(len(client.calls) for client in clients), 2)
        finally:
            filesystem.close()

    def test_bad_subrange_never_publishes_partial_extent(self):
        clients = [FakeRangeClient(MIB * 30, corrupt=True) for _ in range(2)]
        candidate_directory = Path(self.temporary.name) / "bad-subrange-candidate"
        with patch("defeatbeta_api.client.dataset_cache_fs.httpx.Client",
                   side_effect=clients):
            filesystem = DatasetCacheFileSystem(
                directory=str(candidate_directory), version="dataset-v1",
                resolve=lambda url, refresh=False: (SIGNED, MIB * 30),
                max_disk_bytes=16 * MIB,
                network_connections=2, network_chunk_size=MIB // 2,
            )
        try:
            with self.assertRaisesRegex(ValueError, "range"):
                filesystem.cat_file(filesystem.register(PINNED), 0, MIB)
            self.assertFalse(list(candidate_directory.glob("*.block")))
        finally:
            filesystem.close()

    def test_connection_warmup_does_not_fill_the_local_block_cache(self):
        clients = [FakeRangeClient(MIB * 30) for _ in range(2)]
        candidate_directory = Path(self.temporary.name) / "warmup-candidate"
        with patch("defeatbeta_api.client.dataset_cache_fs.httpx.Client",
                   side_effect=clients):
            filesystem = DatasetCacheFileSystem(
                directory=str(candidate_directory), version="dataset-v1",
                resolve=lambda url, refresh=False: (SIGNED, MIB * 30),
                max_disk_bytes=16 * MIB,
                network_connections=2, network_chunk_size=MIB // 2,
            )
        try:
            filesystem.prepare_connections(PINNED, 256 * 1024)
            self.assertEqual([len(client.calls) for client in clients], [1, 1])
            self.assertNotEqual(clients[0].calls[0][1:], clients[1].calls[0][1:])
            self.assertFalse(list(candidate_directory.glob("*.block")))
            self.assertEqual(filesystem.metrics()["cache_misses"], 0)
            self.assertEqual(filesystem.metrics()["range_requests"], 0)
            self.assertEqual(filesystem.metrics()["downloaded_bytes"], 0)
            self.assertEqual(filesystem.warmup_metrics()["range_requests"], 2)
            self.assertEqual(filesystem.warmup_metrics()["downloaded_bytes"], 512 * 1024)
        finally:
            filesystem.close()

    def test_connection_warmup_size_probe_is_not_a_data_download(self):
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "warmup-probe"),
            version="dataset-v1", resolve=lambda url, refresh=False: SIGNED,
            http_client=FakeRangeClient(MIB * 30),
            max_disk_bytes=16 * MIB,
        )
        try:
            filesystem.prepare_connections(PINNED, 1)
            self.assertEqual(filesystem.metrics()["range_requests"], 0)
            self.assertEqual(filesystem.metrics()["downloaded_bytes"], 0)
            self.assertEqual(filesystem.warmup_metrics()["range_requests"], 2)
            self.assertEqual(filesystem.warmup_metrics()["downloaded_bytes"], 2)
        finally:
            filesystem.close()

    def test_connection_warmup_uses_spec_size_without_probe(self):
        remote = FakeRangeClient(MIB * 30)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "warmup-spec-size"),
            version="dataset-v1", resolve=lambda url, refresh=False: SIGNED,
            http_client=remote, max_disk_bytes=16 * MIB,
            footer_index={"US/stock_prices.parquet": {"file_size": MIB * 30}},
        )
        try:
            filesystem.prepare_connections(PINNED, 1)
            self.assertEqual(len(remote.calls), 1)
            self.assertEqual(filesystem.warmup_metrics()["range_requests"], 1)
            self.assertFalse(list(filesystem.directory.glob("*-size.json")))
        finally:
            filesystem.close()

    def test_failed_connection_warmup_does_not_count_invalid_response(self):
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "warmup-invalid"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, MIB * 30),
            http_client=FakeRangeClient(MIB * 30, corrupt=True),
            max_disk_bytes=16 * MIB,
        )
        try:
            with self.assertRaisesRegex(ValueError, "range"):
                filesystem.prepare_connections(PINNED, 1)
            self.assertEqual(filesystem.metrics()["range_requests"], 0)
            self.assertEqual(filesystem.warmup_metrics()["range_requests"], 0)
        finally:
            filesystem.close()

    def test_concurrent_warmup_and_data_read_keep_separate_counters(self):
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "warmup-concurrent"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, MIB * 30),
            http_client=FakeRangeClient(MIB * 30),
            max_disk_bytes=16 * MIB,
        )
        try:
            path = filesystem.register(PINNED)
            with ThreadPoolExecutor(max_workers=2) as executor:
                warmup = executor.submit(filesystem.prepare_connections, PINNED, 1)
                read = executor.submit(filesystem.cat_file, path, 10, 20)
                warmup.result()
                self.assertEqual(read.result(), b"\0" * 10)
            self.assertEqual(filesystem.metrics()["range_requests"], 1)
            self.assertEqual(filesystem.metrics()["downloaded_bytes"], 10)
            self.assertEqual(filesystem.warmup_metrics()["range_requests"], 1)
            self.assertEqual(filesystem.warmup_metrics()["downloaded_bytes"], 1)
        finally:
            filesystem.close()

    def test_download_performance_displays_warmup_separately(self):
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "warmup-report"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, MIB * 30),
            http_client=FakeRangeClient(MIB * 30),
            max_disk_bytes=16 * MIB,
        )
        try:
            filesystem.prepare_connections(PINNED, 1)
            ticker = Ticker.__new__(Ticker)
            ticker.duckdb_client = SimpleNamespace(_dataset_fs=filesystem)
            report = ticker.download_data_performance()
            self.assertIn("Cumulative since client initialization", report)
            data, warmup = report.split("Connection Warmup Performance", 1)
            self.assertIn("downloaded_bytes: 0", data)
            self.assertIn("range_requests: 0", data)
            self.assertIn("downloaded_bytes: 1", warmup)
            self.assertIn("range_requests: 1", warmup)
        finally:
            filesystem.close()

    def test_failed_warmup_waits_for_other_connection_attempts(self):
        second_started = threading.Event()
        release_second = threading.Event()
        with patch("defeatbeta_api.client.dataset_cache_fs.httpx.Client",
                   side_effect=[FakeRangeClient(MIB * 30) for _ in range(2)]):
            filesystem = DatasetCacheFileSystem(
                directory=str(Path(self.temporary.name) / "failed-warmup"),
                version="dataset-v1",
                resolve=lambda url, refresh=False: (SIGNED, MIB * 30),
                max_disk_bytes=16 * MIB,
                network_connections=2,
            )

        def request(_url, _start, _end, _total, lane, *, warmup=False):
            if lane == 0:
                second_started.wait(1)
                raise ValueError("warmup failed")
            second_started.set()
            release_second.wait(1)
            return b"x", MIB * 30

        try:
            with patch.object(filesystem, "_request_range", side_effect=request):
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(filesystem.prepare_connections, PINNED, 1)
                    self.assertTrue(second_started.wait(1))
                    with self.assertRaises(FutureTimeoutError):
                        future.result(timeout=0.1)
                    release_second.set()
                    with self.assertRaisesRegex(ValueError, "warmup failed"):
                        future.result()
        finally:
            release_second.set()
            filesystem.close()

    def test_dead_idle_connection_retries_once_without_refreshing_signed_url(self):
        class StaleClient(FakeRangeClient):
            def get(self, url, headers):
                if not self.calls:
                    self.calls.append((url, *(
                        int(part) for part in headers["Range"][6:].split("-")
                    )))
                    raise httpx.RemoteProtocolError("stale connection")
                return super().get(url, headers)

        remote = StaleClient(MIB * 30)
        self.filesystem._clients = [remote]
        self.filesystem._client = remote
        self.filesystem.resolve = lambda url, refresh=False: (SIGNED, remote.size)
        path = self.filesystem.register(PINNED)

        self.assertEqual(self.filesystem.cat_file(path, 0, 10), b"\0" * 10)
        self.assertEqual(len(remote.calls), 2)
        self.assertEqual({url for url, _, _ in remote.calls}, {SIGNED})
        self.assertEqual(self.filesystem.connection_snapshot()["clients"][0]["transport_errors"], 1)
        self.assertEqual(self.filesystem.connection_snapshot()["clients"][0]["last_result"], "range_ok")

    def test_persistent_transport_failure_is_bounded_and_never_publishes_block(self):
        class FailingClient(FakeRangeClient):
            def get(self, url, headers):
                self.calls.append((url, headers["Range"]))
                raise httpx.ConnectError("unavailable")

        remote = FailingClient(MIB * 30)
        self.filesystem._clients = [remote]
        self.filesystem._client = remote
        self.filesystem.resolve = lambda url, refresh=False: (SIGNED, remote.size)

        with self.assertRaises(httpx.ConnectError):
            self.filesystem.cat_file(self.filesystem.register(PINNED), 0, 10)
        self.assertEqual(len(remote.calls), 2)
        self.assertFalse(list(Path(self.temporary.name).glob("*.block")))

    def test_connection_snapshot_is_observational_and_offline(self):
        self.filesystem.resolve = lambda url, refresh=False: (SIGNED, self.remote.size)
        self.filesystem.cat_file(self.filesystem.register(PINNED), 0, 10)
        request_count = len(self.remote.calls)

        snapshot = self.filesystem.connection_snapshot()
        self.assertEqual(len(self.remote.calls), request_count)
        self.assertEqual(snapshot["tracked_origins"], 1)
        self.assertEqual(snapshot["active_ranges"], 0)
        self.assertEqual(snapshot["clients"][0]["last_result"], "range_ok")
        self.assertNotIn("secret", str(snapshot))
        self.assertNotIn("live", str(snapshot))

    def test_periodic_pool_log_only_reads_observed_state(self):
        filesystem = object.__new__(DatasetCacheFileSystem)
        filesystem._pool_log_stop = Mock()
        filesystem._pool_log_stop.wait.side_effect = [False, True]
        filesystem._pool_logger = Mock()
        filesystem.connection_snapshot = Mock(return_value={
            "observation_only": True, "clients": []
        })

        filesystem._log_connection_pool()

        self.assertEqual(filesystem._pool_log_stop.wait.call_count, 2)
        filesystem.connection_snapshot.assert_called_once_with()
        filesystem._pool_logger.debug.assert_called_once()

    def test_split_extent_is_downloaded_once_for_concurrent_readers(self):
        clients = [FakeRangeClient(MIB * 30) for _ in range(2)]
        with patch("defeatbeta_api.client.dataset_cache_fs.httpx.Client",
                   side_effect=clients):
            filesystem = DatasetCacheFileSystem(
                directory=str(Path(self.temporary.name) / "concurrent-candidate"),
                version="dataset-v1",
                resolve=lambda url, refresh=False: (SIGNED, MIB * 30),
                max_disk_bytes=16 * MIB,
                network_connections=2, network_chunk_size=MIB // 2,
            )
        try:
            path = filesystem.register(PINNED)
            with ThreadPoolExecutor(max_workers=10) as readers:
                results = list(readers.map(
                    lambda _: filesystem.cat_file(path, 0, MIB), range(10)
                ))
            self.assertEqual(results, [b"\0" * MIB] * 10)
            self.assertEqual(sum(len(client.calls) for client in clients), 2)
        finally:
            filesystem.close()

    def test_split_extent_retries_expired_signed_url_without_partial_cache(self):
        class ExpiringClient(FakeRangeClient):
            def get(self, url, headers):
                response = super().get(url, headers)
                if url == SIGNED:
                    response.status_code = 403
                return response

        clients = [ExpiringClient(MIB * 30) for _ in range(2)]
        refreshes = []

        def resolve(url, refresh=False):
            refreshes.append(refresh)
            return ("https://example.test/fresh" if refresh else SIGNED, MIB * 30)

        with patch("defeatbeta_api.client.dataset_cache_fs.httpx.Client",
                   side_effect=clients):
            filesystem = DatasetCacheFileSystem(
                directory=str(Path(self.temporary.name) / "refresh-candidate"),
                version="dataset-v1", resolve=resolve,
                max_disk_bytes=16 * MIB,
                network_connections=2, network_chunk_size=MIB // 2,
            )
        try:
            self.assertEqual(filesystem.cat_file(filesystem.register(PINNED), 0, MIB),
                             b"\0" * MIB)
            self.assertEqual(refreshes.count(True), 2)
            self.assertEqual(len(list(filesystem.directory.glob("*.block"))), 1)
        finally:
            filesystem.close()

    def test_signed_url_refresh_can_move_to_another_origin_pool(self):
        class ExpiringClient(FakeRangeClient):
            def get(self, url, headers):
                response = super().get(url, headers)
                response.status_code = 403
                return response

        clients = [ExpiringClient(MIB * 30), FakeRangeClient(MIB * 30)]

        def resolve(url, refresh=False):
            host = "new.example" if refresh else "old.example"
            return f"https://{host}/file?Signature=secret", MIB * 30

        with patch("defeatbeta_api.client.dataset_cache_fs.httpx.Client",
                   side_effect=clients):
            filesystem = DatasetCacheFileSystem(
                directory=str(Path(self.temporary.name) / "refresh-origin"),
                version="dataset-v1", resolve=resolve,
                max_disk_bytes=16 * MIB,
            )
            try:
                self.assertEqual(
                    filesystem.cat_file(filesystem.register(PINNED), 0, 10),
                    b"\0" * 10,
                )
                self.assertEqual(len(clients[0].calls), 1)
                self.assertEqual(len(clients[1].calls), 1)
                self.assertEqual(len(list(filesystem.directory.glob("*.block"))), 1)
            finally:
                filesystem.close()

    def test_independent_clients_share_the_same_proxy_policy(self):
        clients = [Mock(), Mock()]
        with patch("defeatbeta_api.client.dataset_cache_fs.httpx.Client",
                   side_effect=clients) as constructor:
            filesystem = DatasetCacheFileSystem(
                directory=str(Path(self.temporary.name) / "proxy-candidate"),
                version="dataset-v1", resolve=self._resolve,
                http_proxy="http://proxy.example:8123",
                network_connections=2,
            )
        try:
            self.assertEqual(constructor.call_count, 2)
            for call in constructor.call_args_list:
                self.assertEqual(call.kwargs["proxy"], "http://proxy.example:8123")
                self.assertFalse(call.kwargs["trust_env"])
        finally:
            filesystem.close()

    def test_files_share_connections_by_origin_without_cross_origin_eviction(self):
        clients = [FakeRangeClient(MIB * 30) for _ in range(2)]
        signed = {
            PINNED: "https://cdn.example/prices?Signature=secret",
            PROFILE: "https://cdn.example/profile?Signature=secret",
            CATALOG: "https://huggingface.co/catalog",
        }

        def resolve(url, refresh=False):
            return signed[url], MIB * 30

        with patch("defeatbeta_api.client.dataset_cache_fs.httpx.Client",
                   side_effect=clients) as constructor:
            filesystem = DatasetCacheFileSystem(
                directory=str(Path(self.temporary.name) / "origins"),
                version="dataset-v1", resolve=resolve,
                max_disk_bytes=16 * MIB, network_connections=1,
                http_proxy="http://proxy.example:8123",
            )
            try:
                for url in (PINNED, CATALOG, PROFILE):
                    self.assertEqual(
                        filesystem.cat_file(filesystem.register(url), 0, 10),
                        b"\0" * 10,
                    )
                self.assertEqual(constructor.call_count, 2)
                self.assertEqual(len(clients[0].calls), 2)
                self.assertEqual(len(clients[1].calls), 1)
                self.assertEqual(
                    {urlsplit(call[0]).hostname for call in clients[0].calls},
                    {"cdn.example"},
                )
                self.assertEqual(
                    {urlsplit(call[0]).hostname for call in clients[1].calls},
                    {"huggingface.co"},
                )
                for call in constructor.call_args_list:
                    self.assertEqual(call.kwargs["proxy"], "http://proxy.example:8123")
            finally:
                filesystem.close()

    def test_origin_pool_bounds_idle_groups_without_closing_active_group(self):
        clients = [Mock() for _ in range(5)]
        with patch("defeatbeta_api.client.dataset_cache_fs.httpx.Client",
                   side_effect=clients), patch(
                       "defeatbeta_api.client.dataset_cache_fs._MAX_ORIGIN_GROUPS", 4
                   ):
            filesystem = DatasetCacheFileSystem(
                directory=str(Path(self.temporary.name) / "origin-limit"),
                version="dataset-v1", resolve=self._resolve,
                max_disk_bytes=16 * MIB,
            )
            try:
                _, _, active_origin = filesystem._borrow_client("https://one.example/file")
                for host in ("two", "three", "four", "five"):
                    _, _, origin = filesystem._borrow_client(
                        f"https://{host}.example/file"
                    )
                    filesystem._release_client(origin)
                self.assertEqual(len(filesystem._origin_pools), 4)
                self.assertIn(active_origin, filesystem._origin_pools)
                clients[0].close.assert_not_called()
                clients[1].close.assert_called_once_with()
                filesystem._release_client(active_origin)
            finally:
                filesystem.close()

    def test_concurrent_files_create_one_pool_per_origin(self):
        clients = [FakeRangeClient(MIB * 30) for _ in range(2)]
        signed = {
            PINNED: "https://cdn.example/prices",
            PROFILE: "https://cdn.example/profile",
            CATALOG: "https://huggingface.co/catalog",
        }
        with patch("defeatbeta_api.client.dataset_cache_fs.httpx.Client",
                   side_effect=clients) as constructor:
            filesystem = DatasetCacheFileSystem(
                directory=str(Path(self.temporary.name) / "concurrent-origins"),
                version="dataset-v1",
                resolve=lambda url, refresh=False: (signed[url], MIB * 30),
                max_disk_bytes=16 * MIB,
            )
            try:
                urls = (PINNED, PROFILE, CATALOG) * 8
                with ThreadPoolExecutor(max_workers=12) as executor:
                    contents = list(executor.map(
                        lambda url: filesystem._request_range(url, 0, 0)[0], urls
                    ))
                self.assertEqual(contents, [b"\0"] * len(urls))
                self.assertEqual(constructor.call_count, 2)
                self.assertEqual(len(clients[0].calls), 16)
                self.assertEqual(len(clients[1].calls), 8)
            finally:
                filesystem.close()

    def test_parallel_subranges_are_bounded_by_connection_slots(self):
        barrier = threading.Barrier(2, timeout=1)

        class ConcurrentClient(FakeRangeClient):
            def get(self, url, headers):
                barrier.wait()
                return super().get(url, headers)

        clients = [ConcurrentClient(MIB * 30) for _ in range(2)]
        with patch("defeatbeta_api.client.dataset_cache_fs.httpx.Client",
                   side_effect=clients):
            filesystem = DatasetCacheFileSystem(
                directory=str(Path(self.temporary.name) / "inflight-candidate"),
                version="dataset-v1",
                resolve=lambda url, refresh=False: (SIGNED, MIB * 30),
                max_disk_bytes=16 * MIB, workers=2,
                network_connections=2, network_chunk_size=MIB // 2,
            )
        try:
            self.assertEqual(filesystem._network_executor._max_workers, 2)
            data = filesystem.cat_file(filesystem.register(PINNED), 0, 2 * MIB)
            self.assertEqual(len(data), 2 * MIB)
            self.assertEqual(sum(len(client.calls) for client in clients), 4)
        finally:
            filesystem.close()

    def test_explicit_and_environment_proxy_modes(self):
        for proxy, expected_trust_env in (
            ("http://proxy.example:8123", False),
            (None, True),
            ("", False),
        ):
            with self.subTest(proxy=proxy), patch(
                "defeatbeta_api.client.dataset_cache_fs.httpx.Client"
            ) as http_client:
                filesystem = DatasetCacheFileSystem(
                    directory=self.temporary.name,
                    version="dataset-v1",
                    resolve=self._resolve,
                    http_proxy=proxy,
                )
                try:
                    self.assertEqual(http_client.call_args.kwargs["proxy"], proxy or None)
                    self.assertEqual(
                        http_client.call_args.kwargs["trust_env"], expected_trust_env
                    )
                finally:
                    filesystem.close()

    def test_new_dataset_version_does_not_reuse_old_block(self):
        path = self.filesystem.register(PINNED)
        self.filesystem.cat_file(path, 10, 20)
        old_files = list(Path(self.temporary.name).glob("*.block"))
        self.assertEqual(len(old_files), 1)
        replacement = DatasetCacheFileSystem(
            directory=self.temporary.name,
            version="dataset-v2",
            resolve=self._resolve,
            http_client=self.remote,
            max_disk_bytes=16 * MIB,
            workers=3,
        )
        try:
            replacement.cat_file(replacement.register(PINNED), 10, 20)
            self.assertEqual(len(self.remote.calls), 4)
            self.assertTrue(all(not old_file.exists() for old_file in old_files))
            self.assertEqual(len(list(Path(self.temporary.name).glob("*.block"))), 1)
        finally:
            replacement.close()

    def test_cache_files_are_flat_and_named_for_the_dataset(self):
        path = self.filesystem.register(PINNED)
        self.filesystem.cat_file(path, 10, 20)
        root = Path(self.temporary.name)
        self.assertFalse(any(entry.is_dir() for entry in root.iterdir()))
        self.assertEqual(len(list(root.glob("*stock_prices.parquet-*.block"))), 1)
        self.assertFalse(list(root.glob("*stock_prices.parquet-size.json")))

    def test_old_nested_layout_is_cleaned_without_touching_other_files(self):
        root = Path(self.temporary.name)
        legacy = root / hashlib.sha256(b"old dataset").hexdigest()
        legacy.mkdir()
        (legacy / "size.json").write_text('{"size": 10}', encoding="utf-8")
        (legacy / "0-10.block").write_bytes(b"old")
        unrelated = root / "user-notes.txt"
        unrelated.write_text("keep", encoding="utf-8")
        replacement = DatasetCacheFileSystem(
            directory=self.temporary.name,
            version="dataset-v2",
            resolve=self._resolve,
            http_client=self.remote,
            max_disk_bytes=16 * MIB,
        )
        try:
            self.assertFalse(legacy.exists())
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep")
        finally:
            replacement.close()

    def test_running_filesystem_switches_version_and_discards_old_blocks(self):
        old_path = self.filesystem.register(PINNED)
        self.filesystem.cat_file(old_path, 10, 20)
        self.filesystem.update_version("dataset-v2")
        new_path = self.filesystem.register(PINNED)
        self.assertNotEqual(old_path, new_path)
        self.filesystem.cat_file(new_path, 10, 20)
        self.assertEqual(len(self.remote.calls), 4)
        self.assertEqual(len(list(Path(self.temporary.name).glob("*.block"))), 1)

    def test_running_client_rechecks_dataset_version_before_cached_query(self):
        client = DuckDBClient.__new__(DuckDBClient)
        client.config = Configuration(cache_version_check_seconds=60)
        client._data_update_time = "dataset-v1"
        client._last_version_check = 0
        client._version_lock = threading.Lock()
        client._parquet_index_locks_guard = threading.Lock()
        client._parquet_index_locks = {}
        client._prepared_footers = set()
        client._parquet_indexes = {}
        client._hf_client = Mock()
        client._hf_client.get_data_update_time.return_value = "dataset-v2"
        client._hf_client.dataset_spec = {"footer_index": {
            "US/stock_prices.parquet": {
                "file_size": 100, "footer_size": 20,
                "footer_sha256": "a" * 64,
            },
        }}
        client._dataset_fs = Mock()
        with patch("defeatbeta_api.client.duckdb_client.time.monotonic", return_value=100):
            client._refresh_dataset_version_if_due()
            client._refresh_dataset_version_if_due()
        client._dataset_fs.update_version.assert_called_once_with(
            "dataset-v2", footer_index=client._hf_client.dataset_spec["footer_index"]
        )
        client._dataset_fs.prepare_footer.assert_not_called()
        self.assertEqual(client._data_update_time, "dataset-v2")
        self.assertEqual(client._hf_client.get_data_update_time.call_count, 1)

    def test_occupied_stale_block_is_removed_on_next_cleanup(self):
        path = self.filesystem.register(PINNED)
        self.filesystem.cat_file(path, 10, 20)
        old_block = next(Path(self.temporary.name).glob("*.block"))
        original_unlink = Path.unlink

        def occupied_once(target, *args, **kwargs):
            if target == old_block:
                raise PermissionError("open on Windows")
            return original_unlink(target, *args, **kwargs)

        with patch.object(Path, "unlink", occupied_once):
            self.filesystem.update_version("dataset-v2")
        self.assertTrue(old_block.exists())
        self.filesystem.cleanup_stale()
        self.assertFalse(old_block.exists())

    def test_legacy_directory_with_unknown_file_is_preserved(self):
        legacy = Path(self.temporary.name) / hashlib.sha256(b"other").hexdigest()
        legacy.mkdir()
        (legacy / "notes.txt").write_text("keep", encoding="utf-8")
        self.filesystem.cleanup_stale()
        self.assertTrue((legacy / "notes.txt").exists())

    def test_encoded_dataset_name_is_safe_and_still_cleaned(self):
        encoded = PINNED.replace("stock_prices.parquet", "stock%20prices.parquet")
        path = self.filesystem.register(encoded)
        self.filesystem.cat_file(path, 10, 20)
        old_files = list(Path(self.temporary.name).glob("*.block"))
        self.assertEqual(len(old_files), 1)
        self.filesystem.update_version("dataset-v2")
        self.assertFalse(old_files[0].exists())

    def test_version_switch_does_not_leave_in_flight_old_block(self):
        self.filesystem.resolve = lambda url, refresh=False: (SIGNED, self.remote.size)
        path = self.filesystem.register(PINNED)
        entered = threading.Event()
        release = threading.Event()
        original_write = self.filesystem._atomic_write

        def delayed_write(target, content):
            if target.suffix == ".block":
                entered.set()
                self.assertTrue(release.wait(5))
            return original_write(target, content)

        with patch.object(self.filesystem, "_atomic_write", side_effect=delayed_write):
            with ThreadPoolExecutor(max_workers=2) as tasks:
                reader = tasks.submit(self.filesystem.cat_file, path, 10, 20)
                self.assertTrue(entered.wait(5))
                updater = tasks.submit(self.filesystem.update_version, "dataset-v2")
                release.set()
                self.assertEqual(reader.result(timeout=5), b"\0" * 10)
                updater.result(timeout=5)
        self.assertFalse(list(Path(self.temporary.name).glob("*.block")))

    def test_older_filesystem_cannot_repopulate_after_new_version_wins(self):
        old_path = self.filesystem.register(PINNED)
        self.filesystem.cat_file(old_path, 10, 20)
        replacement = DatasetCacheFileSystem(
            directory=self.temporary.name,
            version="dataset-v2",
            resolve=self._resolve,
            http_client=self.remote,
            max_disk_bytes=16 * MIB,
        )
        try:
            self.assertFalse(list(Path(self.temporary.name).glob("*.block")))
            self.filesystem.max_memory_bytes = 0
            self.filesystem.cat_file(old_path, MIB + 10, MIB + 20)
            self.assertFalse(list(Path(self.temporary.name).glob("*.block")))
        finally:
            replacement.close()

    def test_stale_remote_metadata_cannot_roll_cache_version_back(self):
        newer = DatasetCacheFileSystem(
            directory=self.temporary.name,
            version="2026-09-28T05:48:48Z",
            resolve=self._resolve,
            http_client=self.remote,
            max_disk_bytes=16 * MIB,
        )
        try:
            with self.assertRaisesRegex(ValueError, "older than the active"):
                newer.update_version("2026-09-27T05:48:48Z")
            self.assertEqual(newer.version, "2026-09-28T05:48:48Z")
        finally:
            newer.close()

    def test_same_version_reuses_disk_blocks_after_filesystem_restart(self):
        footer_index = {"US/stock_prices.parquet": {"file_size": self.remote.size}}
        self.filesystem.update_version("dataset-v1", footer_index=footer_index)
        path = self.filesystem.register(PINNED)
        self.filesystem.cat_file(path, 10, 20)
        requests_before_restart = len(self.remote.calls)
        replacement = DatasetCacheFileSystem(
            directory=self.temporary.name,
            version="dataset-v1",
            resolve=self._resolve,
            http_client=self.remote,
            max_disk_bytes=16 * MIB,
            workers=3,
            footer_index=footer_index,
        )
        try:
            replacement.cat_file(replacement.register(PINNED), 10, 20)
            self.assertEqual(len(self.remote.calls), requests_before_restart)
        finally:
            replacement.close()

    def test_expired_signed_url_is_refreshed_once(self):
        self.filesystem.resolve = lambda url, refresh=False: (
            "https://example.test/new" if refresh else SIGNED, self.remote.size
        )
        original_get = self.remote.get

        def reject_old_signature(url, headers):
            if url == SIGNED:
                self.remote.calls.append((url, 0, 0))
                return SimpleNamespace(status_code=403, headers={}, content=b"",
                                       http_version="HTTP/2")
            return original_get(url, headers)

        self.remote.get = reject_old_signature
        path = self.filesystem.register(PINNED)
        self.assertEqual(len(self.filesystem.cat_file(path, 10, 20)), 10)
        self.assertEqual(len(self.remote.calls), 2)

    def test_concurrent_metadata_publish_can_use_existing_size(self):
        import json

        path = self.filesystem.register(PINNED)

        def another_process_won(target, content):
            target.write_text(json.dumps({"size": self.remote.size}), encoding="utf-8")
            raise PermissionError("destination is open on Windows")

        with patch.object(self.filesystem, "_atomic_write",
                          side_effect=another_process_won):
            self.assertEqual(self.filesystem.info(path)["size"], self.remote.size)

    def test_json_catalog_can_be_cached_with_direct_pinned_url(self):
        payload = b'[{"symbol":"AAPL"}]'
        self.remote = FakeRangeClient(len(payload), payload=payload)
        self.filesystem._clients = [self.remote]
        self.filesystem._client = self.remote
        self.filesystem.resolve = lambda url, refresh=False: (url, len(payload))
        path = self.filesystem.register(CATALOG)

        self.assertEqual(self.filesystem.cat_file(path), payload)
        self.assertEqual(self.filesystem.cat_file(path), payload)
        self.assertEqual(len(self.remote.calls), 1)

    def test_explicit_prefetch_fetches_only_requested_ranges(self):
        path = self.filesystem.register(PINNED)
        self.filesystem.prefetch_ranges(path, [(0, 10), (MIB, MIB + 10)])
        self.filesystem.cat_file(path, 0, 10)
        self.filesystem.cat_file(path, MIB, MIB + 10)
        self.assertEqual(len(self.remote.calls), 3)
        self.assertEqual(len(list(Path(self.temporary.name).rglob("*.block"))), 2)

    def test_missing_symbol_does_not_prefetch_unrelated_price_offsets(self):
        client = DuckDBClient.__new__(DuckDBClient)
        client._parquet_indexes = {}
        client._dataset_fs = SimpleNamespace(
            register=Mock(return_value="defeatbeta://abc/stock_prices.parquet"),
            prepare_footer=Mock(),
            cached_footer_bytes=Mock(return_value=FAKE_FOOTER_BYTES),
            prefetch_ranges=Mock(),
        )
        cursor = Mock()
        cursor.execute.return_value.fetchall.return_value = []
        client._get_cursor = lambda: nullcontext(cursor)
        client._to_dataset_sql(f"SELECT * FROM '{PINNED}' WHERE symbol = 'KDP'")
        client._dataset_fs.prefetch_ranges.assert_not_called()

    def test_prefetches_parquet_chunks_for_matching_symbol(self):
        metadata = [
            (0, "symbol", "AAPL", "AAPL", 4, 100),
            (0, "price", None, None, 104, 200),
            (1, "symbol", "KDP", "KDP", 304, 60),
            (1, "price", None, None, 364, 140),
        ]
        client = DuckDBClient.__new__(DuckDBClient)
        client._parquet_indexes = {}
        client._dataset_fs = SimpleNamespace(
            register=Mock(return_value="defeatbeta://abc/stock_prices.parquet"),
            prepare_footer=Mock(),
            cached_footer_bytes=Mock(return_value=FAKE_FOOTER_BYTES),
            prefetch_ranges=Mock(),
        )
        cursor = Mock()
        cursor.execute.return_value.fetchall.return_value = metadata
        client._get_cursor = lambda: nullcontext(cursor)
        sql = f"SELECT * FROM '{PINNED}' WHERE symbol = 'KDP'"
        self.assertIn("defeatbeta://abc/stock_prices.parquet", client._to_dataset_sql(sql))
        client._dataset_fs.prefetch_ranges.assert_called_once_with(
            "defeatbeta://abc/stock_prices.parquet", [(304, 504)]
        )

    def test_prefetches_only_selected_columns_for_news_list(self):
        metadata = [
            (0, "symbol", "AAPL", "AAPL", 4, 100),
            (0, "report_date", None, None, 104, 100),
            (0, "news.list.element.paragraph", None, None, 204, 300),
            (0, "uuid", None, None, 504, 100),
        ]
        client = DuckDBClient.__new__(DuckDBClient)
        client._parquet_indexes = {}
        client._dataset_fs = SimpleNamespace(
            register=Mock(return_value="defeatbeta://abc/stock_news.parquet"),
            prepare_footer=Mock(),
            cached_footer_bytes=Mock(return_value=FAKE_FOOTER_BYTES),
            prefetch_ranges=Mock(),
        )
        cursor = Mock()
        cursor.execute.return_value.fetchall.return_value = metadata
        client._get_cursor = lambda: nullcontext(cursor)
        news_url = PINNED.replace("stock_prices.parquet", "stock_news.parquet")
        sql = (f"SELECT uuid, symbol, report_date FROM '{news_url}' "
               "WHERE symbol = 'AAPL' ORDER BY report_date ASC")
        client._to_dataset_sql(sql)
        client._dataset_fs.prefetch_ranges.assert_called_once_with(
            "defeatbeta://abc/stock_news.parquet", [(4, 204), (504, 604)]
        )

    def test_json_reader_uses_project_cache_path(self):
        client = DuckDBClient.__new__(DuckDBClient)
        client._dataset_fs = SimpleNamespace(
            register=Mock(return_value="defeatbeta://abc/company_tickers.json"),
        )
        sql = f"SELECT * FROM read_json('{CATALOG}', format='array')"
        self.assertEqual(
            client._to_dataset_sql(sql),
            "SELECT * FROM read_json('defeatbeta://abc/company_tickers.json', format='array')",
        )

    def test_duckdb_reads_parquet_through_registered_filesystem(self):
        source = Path(self.temporary.name) / "source.parquet"
        connection = duckdb.connect(":memory:")
        connection.execute("COPY (SELECT range AS value FROM range(10000)) TO ? (FORMAT PARQUET)",
                           [str(source)])
        payload = source.read_bytes()
        self.remote = FakeRangeClient(len(payload), payload=payload)
        self.filesystem._clients = [self.remote]
        self.filesystem._client = self.remote
        path = self.filesystem.register(PINNED)
        connection.register_filesystem(self.filesystem)
        try:
            result = connection.execute(
                f"SELECT SUM(value) FROM read_parquet('{path}')"
            ).fetchone()[0]
            self.assertEqual(result, sum(range(10000)))
        finally:
            connection.close()

    def test_duckdb_reads_parquet_through_io_aligned_cache(self):
        source = Path(self.temporary.name) / "io-source.parquet"
        writer = duckdb.connect(":memory:")
        writer.execute(
            "COPY (SELECT range AS value FROM range(10000)) TO ? (FORMAT PARQUET)",
            [str(source)],
        )
        writer.close()
        payload = source.read_bytes()
        remote = FakeRangeClient(len(payload), payload=payload)
        filesystem = DatasetCacheFileSystem(
            directory=str(Path(self.temporary.name) / "io-duckdb"),
            version="dataset-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(payload)),
            http_client=remote,
            max_disk_bytes=16 * MIB,
        )
        connection = duckdb.connect(":memory:")
        connection.register_filesystem(filesystem)
        try:
            path = filesystem.register(PINNED)
            self.assertEqual(
                connection.execute(f"SELECT SUM(value) FROM read_parquet('{path}')").fetchone()[0],
                sum(range(10000)),
            )
            self.assertTrue(filesystem.read_events())
            self.assertLessEqual(filesystem.metrics()["downloaded_bytes"], len(payload))
        finally:
            connection.close()
            filesystem.close()

    def test_duckdb_reads_json_through_registered_filesystem(self):
        payload = b'[{"symbol":"AAPL"}]'
        self.remote = FakeRangeClient(len(payload), payload=payload)
        self.filesystem._clients = [self.remote]
        self.filesystem._client = self.remote
        self.filesystem.resolve = lambda url, refresh=False: (url, len(payload))
        path = self.filesystem.register(CATALOG)
        connection = duckdb.connect(":memory:")
        connection.register_filesystem(self.filesystem)
        try:
            rows = connection.execute(
                f"SELECT symbol FROM read_json('{path}', format='array')"
            ).fetchall()
            self.assertEqual(rows, [("AAPL",)])
        finally:
            connection.close()

    def test_client_initializes_project_cache_without_community_extension(self):
        with patch(
            "defeatbeta_api.client.hugging_face_client.HuggingFaceClient.get_data_update_time",
            return_value="dataset-v1",
        ), patch("defeatbeta_api.client.duckdb_client._print_welcome"), \
                patch.object(DatasetCacheFileSystem, "prepare_connections") as warmup, \
                patch.object(DatasetCacheFileSystem, "prepare_footer") as footer:
            client = DuckDBClient(config=Configuration(cache_directory=self.temporary.name))
        try:
            self.assertIsInstance(client._dataset_fs, DatasetCacheFileSystem)
            warmup.assert_called_once_with(PINNED, 1)
            footer.assert_not_called()
            self.assertEqual(client.query("SELECT 1").iloc[0, 0], 1)
            loaded = client.connection.execute(
                "SELECT extension_name FROM duckdb_extensions() WHERE loaded"
            ).fetchall()
            self.assertNotIn(("cache_httpfs",), loaded)
        finally:
            client.close()

    def test_startup_warmup_failure_does_not_break_offline_queries_or_leak_url(self):
        with patch(
            "defeatbeta_api.client.hugging_face_client.HuggingFaceClient.get_data_update_time",
            return_value="dataset-v1",
        ), patch("defeatbeta_api.client.duckdb_client._print_welcome"), \
                patch.object(DatasetCacheFileSystem, "prepare_connections",
                             side_effect=RuntimeError("Signature=secret")), \
                self.assertLogs("DuckDBClient", level="WARNING") as captured:
            client = DuckDBClient(config=Configuration(cache_directory=self.temporary.name))
        try:
            self.assertEqual(client.query("SELECT 1").iloc[0, 0], 1)
            self.assertNotIn("secret", " ".join(captured.output))
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
