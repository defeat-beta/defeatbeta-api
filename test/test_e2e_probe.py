"""Keep range-request evidence without changing requests or hiding failures."""

import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
from types import SimpleNamespace

import httpx

from benchmark.e2e.backend import ProductBackend
from benchmark.e2e.probe import observe_ranges


class TestBackendDiskReuse(unittest.TestCase):
    def test_restart_preserves_disk_files_but_cold_reset_removes_them(self):
        with tempfile.TemporaryDirectory() as directory:
            first = ProductBackend(directory)
            first.reset()
            marker = first.cache_directory / "retained.block"
            marker.write_bytes(b"validated cached data")
            first.close()
            restarted = ProductBackend(directory)
            try:
                restarted.reset(preserve_disk=True)
                self.assertEqual(marker.read_bytes(), b"validated cached data")
                self.assertFalse(restarted._tickers)
                self.assertIsNotNone(restarted._config)
                restarted.reset()
                self.assertFalse(marker.exists())
                self.assertTrue(restarted.cache_directory.is_dir())
            finally:
                restarted.close()

    def test_reuse_requires_the_first_round_directory_to_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = ProductBackend(directory)
            try:
                with self.assertRaisesRegex(ValueError, "existing disk cache"):
                    backend.reset(preserve_disk=True)
                self.assertFalse(backend.cache_directory.exists())
            finally:
                backend.close()


class TestRangeEvidence(unittest.TestCase):
    def test_failed_range_retains_offsets_original_error_and_redacted_cause(self):
        from defeatbeta_api.client.dataset_cache_fs import DatasetCacheFileSystem

        def fail(filesystem, *args, **kwargs):
            try:
                raise TimeoutError("https://cdn.test/data?token=private")
            except TimeoutError as cause:
                raise httpx.ReadTimeout("Expected read timeout") from cause

        filesystem = object.__new__(DatasetCacheFileSystem)
        with patch.object(DatasetCacheFileSystem, "_request_range", fail):
            with observe_ranges() as evidence:
                with self.assertRaises(httpx.ReadTimeout):
                    filesystem._request_range("https://example.test/input.parquet", 10, 19, 100)
        self.assertEqual(evidence["request_count"], 1)
        event = evidence["events"][0]
        self.assertEqual((event["file"], event["start"], event["end"]), ("input.parquet", 10, 19))
        self.assertEqual(event["error_type"], "ReadTimeout")
        self.assertEqual(event["causes"][0]["error_type"], "TimeoutError")
        self.assertNotIn("private", str(event))

    def test_size_and_connection_probes_remain_counted(self):
        from defeatbeta_api.client.dataset_cache_fs import DatasetCacheFileSystem

        filesystem = object.__new__(DatasetCacheFileSystem)
        with patch.object(DatasetCacheFileSystem, "_request_range", return_value=(b"x", 100)):
            with observe_ranges() as evidence:
                filesystem._request_range("https://example.test/input.json", 0, 0)
                filesystem._request_range("https://example.test/input.json", 0, 0, 100)
                filesystem._request_range("https://example.test/input.parquet", 24, 24, 100, warmup=True)
        self.assertEqual(evidence["request_count"], 3)
        self.assertEqual([event["purpose"] for event in evidence["events"]],
                         ["size_probe", "data", "connection_warmup"])
        self.assertTrue(all(event["status"] == "ok" for event in evidence["events"]))

    def test_request_count_stays_exact_when_trace_is_bounded(self):
        from defeatbeta_api.client.dataset_cache_fs import DatasetCacheFileSystem

        filesystem = object.__new__(DatasetCacheFileSystem)
        with patch.object(DatasetCacheFileSystem, "_request_range", return_value=(b"x", 100)):
            with observe_ranges() as evidence:
                for _ in range(5000):
                    filesystem._request_range("https://example.test/input.json", 0, 0)
        self.assertEqual(evidence["request_count"], 5000)
        self.assertLess(len(evidence["events"]), 5000)
        self.assertFalse(evidence["events_complete"])


class TestProductCounterEvidence(unittest.TestCase):
    def test_shared_filesystem_is_counted_once_and_deltas_exclude_prior_calls(self):
        from defeatbeta_api.client.dataset_cache_fs import DatasetCacheFileSystem

        counters = {"cache_hits": 10, "cache_misses": 20, "downloaded_bytes": 500,
                    "range_requests": 30, "range_seconds": 1.0}
        filesystem = SimpleNamespace(metrics=lambda: counters.copy())
        client = SimpleNamespace(_dataset_fs=filesystem)
        backend = ProductBackend.__new__(ProductBackend)
        backend._tickers = {symbol: SimpleNamespace(duckdb_client=client) for symbol in ("A", "B")}
        raw = object.__new__(DatasetCacheFileSystem)
        with patch.object(DatasetCacheFileSystem, "_request_range", return_value=(b"x", 100)):
            with backend.probe() as evidence:
                counters["cache_misses"] += 2
                counters["downloaded_bytes"] += 50
                counters["range_requests"] += 3
                raw._request_range("https://example.test/input.json", 0, 0)
        self.assertEqual(evidence["metrics"]["cache_misses"], 2)
        self.assertEqual(evidence["metrics"]["downloaded_bytes"], 50)
        self.assertEqual(evidence["metrics"]["range_requests"], 3)
        self.assertEqual(evidence["request_count"], 1)
        with backend.probe() as repeat:
            pass
        self.assertEqual(repeat["metrics"]["cache_misses"], 0)

    def test_distinct_filesystems_are_summed_after_async_drain(self):
        counters = [{"cache_hits": 0, "cache_misses": 0, "downloaded_bytes": 0,
                     "range_requests": 0, "range_seconds": 0.0} for _ in range(2)]
        backend = ProductBackend.__new__(ProductBackend)
        backend._tickers = {str(index): SimpleNamespace(duckdb_client=SimpleNamespace(
            _dataset_fs=SimpleNamespace(metrics=lambda c=c: c.copy()))) for index, c in enumerate(counters)}
        with backend.probe() as evidence:
            counters[0]["cache_misses"] += 2
            counters[1]["cache_misses"] += 3
        self.assertEqual(evidence["metrics"]["cache_misses"], 5)
