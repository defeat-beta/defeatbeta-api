"""Tests for bounded, demand-driven dataset block caching."""

import tempfile
import threading
import unittest
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
        finally:
            replacement.close()

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
