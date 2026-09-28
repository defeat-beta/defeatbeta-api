"""Tests for bounded, demand-driven dataset block caching."""

import tempfile
import threading
import unittest
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import duckdb

from defeatbeta_api.client.dataset_cache_fs import DatasetCacheFileSystem
from defeatbeta_api.client.duckdb_client import DuckDBClient
from defeatbeta_api.client.duckdb_conf import Configuration


MIB = 1024 * 1024
PINNED = (
    "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data"
    "/resolve/main/data/US/stock_prices.parquet"
)
SIGNED = "https://example.test/object?Signature=secret"
CATALOG = (
    "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data"
    "/resolve/main/data/US/company_tickers.json"
)


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
            block_size=MIB,
            max_disk_bytes=16 * MIB,
            workers=3,
        )

    def tearDown(self):
        self.filesystem.close()
        self.temporary.cleanup()

    def _resolve(self, url, refresh=False):
        self.resolutions.append((url, refresh))
        return SIGNED

    def test_rejects_disk_limit_smaller_than_one_block(self):
        with self.assertRaisesRegex(ValueError, "block size"):
            DatasetCacheFileSystem(
                directory=self.temporary.name,
                version="dataset-v1",
                resolve=self._resolve,
                block_size=MIB,
                max_disk_bytes=MIB - 1,
                http_client=self.remote,
            )

    def test_large_file_fetches_only_demanded_blocks_and_reuses_them(self):
        path = self.filesystem.register(PINNED)
        self.assertEqual(self.filesystem.cat_file(path, 10, 20), b"\0" * 10)
        tail = self.remote.size - 50
        self.assertEqual(len(self.filesystem.cat_file(path, tail, tail + 10)), 10)
        self.assertEqual(len(self.remote.calls), 3)
        last_block_bytes = self.remote.size % MIB
        self.assertEqual(sum(end - start + 1 for _, start, end in self.remote.calls),
                         1 + MIB + last_block_bytes)

        self.filesystem.cat_file(path, 10, 20)
        self.filesystem.cat_file(path, tail, tail + 10)
        self.assertEqual(len(self.remote.calls), 3)
        self.assertEqual(len(self.resolutions), 4)
        self.assertNotIn("Signature", " ".join(
            str(item) for item in Path(self.temporary.name).rglob("*")
        ))

    def test_bad_range_does_not_publish_block(self):
        self.remote.corrupt = True
        path = self.filesystem.register(PINNED)
        with self.assertRaisesRegex(ValueError, "range"):
            self.filesystem.cat_file(path, MIB, MIB + 10)
        self.assertFalse(list(Path(self.temporary.name).rglob("*.block")))

    def test_same_length_disk_corruption_is_refetched(self):
        self.filesystem.max_memory_blocks = 0
        path = self.filesystem.register(PINNED)
        self.filesystem.cat_file(path, 0, 10)
        block = next(Path(self.temporary.name).rglob("*.block"))
        block.write_bytes(b"x" * block.stat().st_size)

        self.assertEqual(self.filesystem.cat_file(path, 0, 10), b"\0" * 10)
        self.assertEqual(len(self.remote.calls), 3)

    def test_disk_eviction_keeps_recent_demanded_blocks(self):
        self.filesystem.max_memory_blocks = 0
        self.filesystem.max_disk_bytes = 2 * MIB + 64
        path = self.filesystem.register(PINNED)
        for start in (0, MIB, 2 * MIB):
            self.filesystem.cat_file(path, start, start + 10)

        self.assertLessEqual(
            sum(block.stat().st_size for block in Path(self.temporary.name).rglob("*.block")),
            self.filesystem.max_disk_bytes,
        )

    def test_resolve_head_size_avoids_probe_range(self):
        self.filesystem.resolve = lambda url, refresh=False: (SIGNED, self.remote.size)
        path = self.filesystem.register(PINNED)
        self.filesystem.cat_file(path, 10, 20)
        self.assertEqual(len(self.remote.calls), 1)
        self.assertEqual(self.remote.calls[0][1:], (0, MIB - 1))

    def test_hot_block_is_served_without_another_disk_read(self):
        path = self.filesystem.register(PINNED)
        self.filesystem.cat_file(path, 10, 20)
        with patch.object(self.filesystem, "_read_block",
                          side_effect=AssertionError("hot block reread from disk")):
            self.assertEqual(self.filesystem.cat_file(path, 10, 20), b"\0" * 10)

    def test_memory_lru_respects_configured_block_limit(self):
        self.filesystem.max_memory_blocks = 2
        path = self.filesystem.register(PINNED)
        for start in (0, MIB, 2 * MIB):
            self.filesystem.cat_file(path, start, start + 10)
        self.assertEqual(len(self.filesystem._memory_blocks), 2)

    def test_concurrent_readers_share_one_range_download(self):
        self.filesystem.resolve = lambda url, refresh=False: (SIGNED, self.remote.size)
        path = self.filesystem.register(PINNED)
        with ThreadPoolExecutor(max_workers=10) as readers:
            results = list(readers.map(
                lambda _: self.filesystem.cat_file(path, 0, 10), range(10)
            ))
        self.assertEqual(results, [b"\0" * 10] * 10)
        self.assertEqual(len(self.remote.calls), 1)

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
            block_size=MIB,
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
        self.assertEqual(len(list(root.glob("*stock_prices.parquet-size.json"))), 1)

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
            block_size=MIB,
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
        client._hf_client = Mock()
        client._hf_client.get_data_update_time.return_value = "dataset-v2"
        client._dataset_fs = Mock()
        with patch("defeatbeta_api.client.duckdb_client.time.monotonic", return_value=100):
            client._refresh_dataset_version_if_due()
            client._refresh_dataset_version_if_due()
        client._dataset_fs.update_version.assert_called_once_with("dataset-v2")
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
            block_size=MIB,
            max_disk_bytes=16 * MIB,
        )
        try:
            self.assertFalse(list(Path(self.temporary.name).glob("*.block")))
            self.filesystem.max_memory_blocks = 0
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
            block_size=MIB,
            max_disk_bytes=16 * MIB,
        )
        try:
            with self.assertRaisesRegex(ValueError, "older than the active"):
                newer.update_version("2026-09-27T05:48:48Z")
            self.assertEqual(newer.version, "2026-09-28T05:48:48Z")
        finally:
            newer.close()

    def test_same_version_reuses_disk_blocks_after_filesystem_restart(self):
        path = self.filesystem.register(PINNED)
        self.filesystem.cat_file(path, 10, 20)
        requests_before_restart = len(self.remote.calls)
        replacement = DatasetCacheFileSystem(
            directory=self.temporary.name,
            version="dataset-v1",
            resolve=self._resolve,
            http_client=self.remote,
            block_size=MIB,
            max_disk_bytes=16 * MIB,
            workers=3,
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
        self.filesystem._client = self.remote
        self.filesystem.resolve = lambda url, refresh=False: (url, len(payload))
        path = self.filesystem.register(CATALOG)

        self.assertEqual(self.filesystem.cat_file(path), payload)
        self.assertEqual(self.filesystem.cat_file(path), payload)
        self.assertEqual(len(self.remote.calls), 1)

    def test_explicit_price_prefetch_fetches_only_three_candidate_blocks(self):
        path = self.filesystem.register(PINNED)
        self.filesystem.prefetch(path)
        self.filesystem.cat_file(path, 0, 10)
        self.filesystem.cat_file(path, MIB, MIB + 10)
        self.filesystem.cat_file(path, self.remote.size - 10, self.remote.size)
        self.assertEqual(len(self.remote.calls), 4)
        self.assertEqual(len(list(Path(self.temporary.name).rglob("*.block"))), 3)

    def test_price_query_prefetch_is_not_applied_to_other_queries(self):
        client = DuckDBClient.__new__(DuckDBClient)
        client._dataset_fs = SimpleNamespace(
            register=Mock(return_value="defeatbeta://abc/stock_prices.parquet"),
            prefetch=Mock(),
        )
        price_sql = f"SELECT * FROM '{PINNED}' WHERE symbol = 'AAPL'"
        client._to_dataset_sql(price_sql)
        client._dataset_fs.prefetch.assert_called_once()

        client._dataset_fs.prefetch.reset_mock()
        client._to_dataset_sql(f"SELECT COUNT(*) FROM '{PINNED}'")
        client._dataset_fs.prefetch.assert_not_called()

    def test_json_reader_uses_project_cache_path(self):
        client = DuckDBClient.__new__(DuckDBClient)
        client._dataset_fs = SimpleNamespace(
            register=Mock(return_value="defeatbeta://abc/company_tickers.json"),
            prefetch=Mock(),
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

    def test_duckdb_reads_json_through_registered_filesystem(self):
        payload = b'[{"symbol":"AAPL"}]'
        self.remote = FakeRangeClient(len(payload), payload=payload)
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
        ), patch("defeatbeta_api.client.duckdb_client._print_welcome"):
            client = DuckDBClient(config=Configuration(cache_directory=self.temporary.name))
        try:
            self.assertIsInstance(client._dataset_fs, DatasetCacheFileSystem)
            self.assertEqual(client.query("SELECT 1").iloc[0, 0], 1)
            loaded = client.connection.execute(
                "SELECT extension_name FROM duckdb_extensions() WHERE loaded"
            ).fetchall()
            self.assertNotIn(("cache_httpfs",), loaded)
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
