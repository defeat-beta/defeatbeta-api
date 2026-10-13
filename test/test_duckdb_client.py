import logging
import inspect
import io
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Barrier, Event, Lock, current_thread
from types import SimpleNamespace
from unittest.mock import Mock, patch

from defeatbeta_api.client.duckdb_client import DuckDBClient, capture_performance
from defeatbeta_api.client.duckdb_client import Configuration
from defeatbeta_api.client.dataset_cache_fs import DatasetCacheFileSystem


FAKE_FOOTER_BYTES = b"meta" + (4).to_bytes(4, "little") + b"PAR1"


def metadata_cursor(rows, delay=0):
    cursor = Mock()

    def execute(*args):
        if delay:
            time.sleep(delay)
        return SimpleNamespace(fetchall=lambda: rows)

    cursor.execute.side_effect = execute

    @contextmanager
    def get_cursor():
        yield cursor

    return get_cursor, cursor


class TestDuckDBClient(unittest.TestCase):

    def test_inflight_query_retries_as_a_whole_after_version_change(self):
        import duckdb
        from defeatbeta_api.client.shared_resources import SharedCache
        from test.test_dataset_cache_fs import FakeRangeClient, PINNED

        for cached in (True, False):
            for new_rows in (8192, 8193):
                with self.subTest(cached=cached, new_rows=new_rows), \
                        tempfile.TemporaryDirectory() as directory, patch(
                            "defeatbeta_api.client.duckdb_client.RESOLVED_URLS", SharedCache()):
                    con = duckdb.connect()
                    objects = {}
                    expected = {}
                    for name, rows, first, second in (
                            ("old", 8192, "AAA", "BBB"),
                            ("new", new_rows, "BBB", "AAA")):
                        path = str(Path(directory) / f"{name}.parquet")
                        con.execute(
                            "COPY (SELECT CASE WHEN i < 4096 THEN ? ELSE ? END AS symbol, "
                            "i, md5(i::VARCHAR) || md5((i + 1)::VARCHAR) AS payload "
                            "FROM range(?) t(i)) TO ? "
                            "(FORMAT PARQUET, ROW_GROUP_SIZE 2048, COMPRESSION UNCOMPRESSED)",
                            [first, second, rows, path])
                        payload = Path(path).read_bytes()
                        objects[f"https://cdn.test/{name}"] = FakeRangeClient(
                            len(payload), payload=payload)
                        expected[name] = con.execute(
                            "SELECT count(*), sum(i) FROM read_parquet(?) WHERE symbol = 'AAA'",
                            [path]).fetchone()
                    if new_rows == 8192:
                        self.assertEqual(objects["https://cdn.test/old"].size,
                                         objects["https://cdn.test/new"].size)
                    client = self.resolution_client()
                    old_version = client._data_update_time
                    client.connection = con
                    client.logger = Mock()
                    client._has_shared_network = True
                    client._network_fs_lock = Lock()
                    client._hf_client.get_shared_data_update_time.return_value = old_version

                    def resolve(*args, **kwargs):
                        name = "old" if client._data_update_time == old_version else "new"
                        url = f"https://cdn.test/{name}"
                        return url, objects[url].size

                    client._hf_client.resolve_cdn_info.side_effect = resolve
                    remote = SimpleNamespace(get=lambda url, headers: objects[url].get(url, headers))
                    fs = DatasetCacheFileSystem(
                        directory=str(Path(directory) / "cache"), version=old_version,
                        resolve=client._resolve_for_dataset, http_client=remote,
                        cache_enabled=cached)
                    if cached:
                        client._dataset_fs = fs
                        client._get_uncached_filesystem = Mock(
                            side_effect=AssertionError("Version retry must keep the selected reader"))
                    else:
                        client._uncached_fs = fs
                        client._get_uncached_filesystem = lambda: fs
                    con.register_filesystem(fs)
                    entered, release = Event(), Event()
                    request_range = fs._request_range

                    def gated_range(url, start, end, *args, **kwargs):
                        # Hold the first data read after DuckDB has bound the old footer.
                        if start < 4096 and not entered.is_set():
                            entered.set()
                            if not release.wait(5):
                                raise TimeoutError("Data read was not released")
                        return request_range(url, start, end, *args, **kwargs)

                    fs._request_range = gated_range
                    sql = f"SELECT count(*) AS n, sum(i) AS total FROM '{PINNED}' WHERE symbol = 'AAA'"
                    try:
                        with ThreadPoolExecutor(max_workers=1) as executor:
                            result = executor.submit(client.query, sql)
                            try:
                                self.assertTrue(entered.wait(3))
                                client._hf_client.get_shared_data_update_time.return_value = (
                                    "2026-10-13T00:00:00Z")
                                client._refresh_dataset_version_if_due(use_dataset_cache=cached)
                            finally:
                                release.set()
                            frame = result.result(timeout=5)
                        self.assertEqual(tuple(frame.iloc[0]), expected["new"])
                    finally:
                        con.unregister_filesystem(fs.protocol)
                        fs.close()
                        con.close()

    def resolution_client(self):
        client = DuckDBClient.__new__(DuckDBClient)
        client._cdn_lock = Lock()
        client._dataset_cdn_cache = {}
        client._resolve_ttl = 1800
        client.http_proxy = ""
        client._data_update_time = "2026-10-12T00:00:00Z"
        client.config = Configuration(cache_version_check_interval_seconds=0)
        client._version_lock = Lock()
        client._last_version_check = float("-inf")
        client._footer_index = {}
        client._parquet_indexes = {}
        client._parquet_index_locks_guard = Lock()
        client._prepared_footers = set()
        client._dataset_fs = None
        client._hf_client = SimpleNamespace(
            resolve_cdn_info=Mock(), dataset_spec={},
            get_shared_data_update_time=Mock(return_value="2026-10-13T00:00:00Z"))
        return client

    def test_query_validates_generation_after_result_materialization(self):
        client = self.resolution_client()
        client.logger = Mock()
        old = client._data_update_time
        client._hf_client.get_shared_data_update_time.return_value = old

        def execute(*args, **kwargs):
            if client._data_update_time == old:
                client._hf_client.get_shared_data_update_time.return_value = "new"
                client._refresh_dataset_version_if_due()
                return "stale materialized result"
            return "new result"

        client._execute_query = Mock(side_effect=execute)
        self.assertEqual(client._query_dataset("query"), "new result")
        self.assertEqual(client._execute_query.call_count, 2)

    def test_repeated_generation_changes_stop_without_cache_fallback(self):
        from defeatbeta_api.client.dataset_cache_fs import DatasetVersionChanged
        from test.test_dataset_cache_fs import PINNED

        for cached in (True, False):
            with self.subTest(cached=cached):
                client = self.resolution_client()
                client.logger = Mock()
                client._has_shared_network = True
                client._dataset_fs = Mock(version=client._data_update_time, _footer_index={}) if cached else None
                client._get_uncached_filesystem = Mock(return_value=None)
                client._hf_client.get_shared_data_update_time.return_value = client._data_update_time

                def execute(*args, **kwargs):
                    client._hf_client.get_shared_data_update_time.return_value = (
                        str(client._execute_query.call_count))
                    client._refresh_dataset_version_if_due(use_dataset_cache=cached)
                    return "stale result"

                client._execute_query = Mock(side_effect=execute)
                with self.assertRaisesRegex(DatasetVersionChanged, "Dataset changed during both query attempts"):
                    client.query(f"SELECT * FROM '{PINNED}'")
                self.assertEqual(client._execute_query.call_count, 2)
                if cached:
                    client._get_uncached_filesystem.assert_not_called()

    def test_unchanged_generation_preserves_query_error_without_retry(self):
        client = self.resolution_client()
        failure = ValueError("Invalid query")
        client._execute_query = Mock(side_effect=failure)
        with self.assertRaises(ValueError) as raised:
            client._query_dataset("query")
        self.assertIs(raised.exception, failure)
        self.assertEqual(client._execute_query.call_count, 1)

    def test_version_validation_does_not_serialize_concurrent_queries(self):
        client = self.resolution_client()
        client._hf_client.get_shared_data_update_time.return_value = client._data_update_time
        together = Barrier(2, timeout=3)

        def execute(sql, **kwargs):
            together.wait()
            return sql

        client._execute_query = execute
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(client._query_dataset, ("first", "second")))
        self.assertEqual(results, ["first", "second"])

    def test_dataset_version_refresh_invalidates_resolved_object(self):
        from defeatbeta_api.client.shared_resources import SharedCache

        for cached in (True, False):
            for new_size in (100, 101):
                with self.subTest(cached=cached, new_size=new_size), patch(
                        "defeatbeta_api.client.duckdb_client.RESOLVED_URLS", SharedCache()):
                    client = self.resolution_client()
                    client._hf_client.resolve_cdn_info.side_effect = [
                        ("https://cdn.test/old", 100), ("https://cdn.test/new", new_size)]
                    self.assertEqual(client._resolve_for_dataset("pinned-url"),
                                     ("https://cdn.test/old", 100))
                    client._refresh_dataset_version_if_due(use_dataset_cache=cached)
                    for _ in range(2):
                        self.assertEqual(client._resolve_for_dataset("pinned-url"),
                                         ("https://cdn.test/new", new_size))
                    self.assertEqual(client._hf_client.resolve_cdn_info.call_count, 2)

    def test_old_inflight_resolution_cannot_replace_new_version(self):
        from defeatbeta_api.client.shared_resources import SharedCache

        client = self.resolution_client()
        entered, release = Event(), Event()

        def resolve(*args, **kwargs):
            if not entered.is_set():
                entered.set()
                if not release.wait(5):
                    raise TimeoutError("Old resolution was not released")
                return "https://cdn.test/old", 100
            return "https://cdn.test/new", 100

        client._hf_client.resolve_cdn_info.side_effect = resolve
        with patch("defeatbeta_api.client.duckdb_client.RESOLVED_URLS", SharedCache()):
            with ThreadPoolExecutor(max_workers=1) as executor:
                old = executor.submit(client._resolve_for_dataset, "pinned-url")
                try:
                    self.assertTrue(entered.wait(3))
                    client._refresh_dataset_version_if_due()
                    self.assertEqual(client._resolve_for_dataset("pinned-url"),
                                     ("https://cdn.test/new", 100))
                finally:
                    release.set()
                self.assertEqual(old.result(timeout=3), ("https://cdn.test/old", 100))
            self.assertEqual(client._resolve_for_dataset("pinned-url"),
                             ("https://cdn.test/new", 100))
            self.assertEqual(client._hf_client.resolve_cdn_info.call_count, 2)

    def test_version_refresh_reads_new_bytes_with_and_without_disk_cache(self):
        from defeatbeta_api.client.shared_resources import SharedCache
        from test.test_dataset_cache_fs import FakeRangeClient, PINNED

        for cached in (True, False):
            for new_size in (100, 101):
                with self.subTest(cached=cached, new_size=new_size), \
                        tempfile.TemporaryDirectory() as directory, patch(
                            "defeatbeta_api.client.duckdb_client.RESOLVED_URLS", SharedCache()):
                    client = self.resolution_client()
                    old_url, new_url = "https://cdn.test/old", "https://cdn.test/new"
                    objects = {old_url: FakeRangeClient(100, payload=b"a" * 100),
                               new_url: FakeRangeClient(new_size, payload=b"b" * new_size)}
                    remote = SimpleNamespace(get=lambda url, headers: objects[url].get(url, headers))
                    client._hf_client.resolve_cdn_info.side_effect = [
                        (old_url, 100), (new_url, new_size)]
                    filesystem = DatasetCacheFileSystem(
                        directory=directory, version=client._data_update_time,
                        resolve=client._resolve_for_dataset, http_client=remote,
                        cache_enabled=cached)
                    if cached:
                        client._dataset_fs = filesystem
                    else:
                        client._uncached_fs = filesystem
                    try:
                        self.assertEqual(filesystem.cat_file(filesystem.register(PINNED), 0, 100),
                                         b"a" * 100)
                        client._refresh_dataset_version_if_due(use_dataset_cache=cached)
                        path = filesystem.register(PINNED)
                        for _ in range(2):
                            self.assertEqual(filesystem.cat_file(path, 0, new_size), b"b" * new_size)
                        self.assertEqual(client._hf_client.resolve_cdn_info.call_count, 2)
                        self.assertEqual(len(objects[old_url].calls), 1)
                        self.assertEqual(len(objects[new_url].calls), 1 if cached else 2)
                    finally:
                        filesystem.close()

    def test_resolution_reuses_latest_shared_refresh_and_separates_routes(self):
        from defeatbeta_api.client.shared_resources import SharedCache

        first, second = self.resolution_client(), self.resolution_client()
        remote = Mock(side_effect=[("old", 100), ("renewed", 100), ("other-route", 100)])
        first._hf_client.resolve_cdn_info = second._hf_client.resolve_cdn_info = remote
        with patch("defeatbeta_api.client.duckdb_client.RESOLVED_URLS", SharedCache()):
            self.assertEqual(first._resolve_for_dataset("pinned-url"), ("old", 100))
            self.assertEqual(second._resolve_for_dataset("pinned-url"), ("old", 100))
            self.assertEqual(second._resolve_for_dataset("pinned-url", refresh=True),
                             ("renewed", 100))
            self.assertEqual(first._resolve_for_dataset("pinned-url"), ("renewed", 100))
            first.http_proxy = "http://proxy.test:8080"
            self.assertEqual(first._resolve_for_dataset("pinned-url"), ("other-route", 100))
            self.assertEqual(remote.call_count, 3)

    def test_shared_client_is_closed_before_interpreter_shutdown(self):
        script = textwrap.dedent('''
            import tempfile
            import duckdb
            from unittest.mock import patch
            from defeatbeta_api.client.duckdb_client import (
                Configuration, DuckDBClient, get_duckdb_client,
            )

            def initialize(client):
                client.connection = duckdb.connect(config={"threads": 1})

            def load_version(client):
                client._data_update_time = "shutdown-fixture-v1"

            with tempfile.TemporaryDirectory() as directory:
                with patch.object(DuckDBClient, "_initialize_connection", initialize), \\
                        patch.object(DuckDBClient, "_load_dataset_version", load_version):
                    config = Configuration(cache_directory=directory)
                    client = get_duckdb_client(config=config)
                    assert get_duckdb_client(config=config) is client
                    assert client.connection.sql("SELECT 42").fetchone() == (42,)
                    original_close = client.close

                    def close():
                        original_close()
                        print("shared-client-closed", flush=True)

                    client.close = close
        ''')
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True,
            timeout=20, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("shared-client-closed"), 1, result.stderr)
        self.assertNotIn("nanobind: leaked", result.stderr)
        self.assertNotIn("Exception ignored in atexit", result.stderr)

    def test_shared_shutdown_drains_registry_and_continues_after_close_failure(self):
        import defeatbeta_api.client.duckdb_client as module

        first = Mock()
        first.close.side_effect = RuntimeError("Close failed")
        second = Mock()
        registry = {"first": first, "second": second}
        with patch.object(module, "_instances", registry):
            with self.assertRaisesRegex(RuntimeError, "Close failed"):
                module._close_shared_duckdb_clients()
            self.assertEqual(registry, {})
            first.close.assert_called_once_with()
            second.close.assert_called_once_with()
            module._close_shared_duckdb_clients()
            second.close.assert_called_once_with()

    def test_version_refresh_cache_failure_does_not_block_network_fallback(self):
        client = DuckDBClient.__new__(DuckDBClient)
        client.config = Configuration(cache_version_check_interval_seconds=60)
        client._last_version_check = float("-inf")
        client._version_lock = Lock()
        client._parquet_index_locks_guard = Lock()
        client._parquet_indexes = {}
        client._data_update_time = "old"
        client._footer_index = {}
        client._hf_client = SimpleNamespace(
            get_shared_data_update_time=Mock(return_value="new"), dataset_spec={})
        cached = SimpleNamespace(version="old", _footer_index={})
        cached.update_version = Mock(side_effect=OSError("Cache directory is read-only"))
        network = SimpleNamespace(version="old", _footer_index={})

        def update_network(version, footer_index):
            network.version = version
            network._footer_index = footer_index

        network.update_version = Mock(side_effect=update_network)
        client._dataset_fs = cached
        client._uncached_fs = network
        client._has_shared_network = True
        client._get_uncached_filesystem = Mock(return_value=network)
        client.logger = Mock()
        client._execute_query = Mock(return_value="network result")
        url = ("https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/"
               "resolve/main/data/US/stock_prices.parquet")
        sql = f"SELECT * FROM '{url}'"

        self.assertEqual(client.query(sql), "network result")
        client._execute_query.assert_called_once_with(
            sql, use_dataset_cache=True, filesystem=network)
        self.assertEqual(network.version, "new")
        self.assertEqual(cached.update_version.call_count, 1)

        def recover_cache(version, footer_index):
            cached.version = version
            cached._footer_index = footer_index

        cached.update_version.side_effect = recover_cache
        client._execute_query.reset_mock()
        client.query(sql)
        self.assertEqual(cached.version, "new")
        client._execute_query.assert_called_once_with(sql, use_dataset_cache=True)

    def test_concurrent_forced_url_refresh_does_not_return_invalid_generation(self):
        from defeatbeta_api.client.shared_resources import SharedCache

        client = DuckDBClient.__new__(DuckDBClient)
        client._version_lock = Lock()
        client._cdn_lock = Lock()
        client._dataset_cdn_cache = {}
        client._resolve_ttl = 3600
        client.http_proxy = ""
        client._data_update_time = "version"
        client._hf_client = SimpleNamespace(resolve_cdn_info=Mock(
            side_effect=[("old-url", 100), ("new-url", 100)]))
        paused, resume = Event(), Event()
        worker = []

        def identity(*args):
            if worker and current_thread() is worker[0]:
                paused.set()
                if not resume.wait(3):
                    raise TimeoutError("Refresh was not resumed")
            return (None, None, None)

        def first_refresh():
            worker.append(current_thread())
            return client._resolve_for_dataset("pinned-url", refresh=True)

        with patch("defeatbeta_api.client.duckdb_client.RESOLVED_URLS", SharedCache()), \
                patch("defeatbeta_api.client.duckdb_client.network_identity", identity):
            self.assertEqual(client._resolve_for_dataset("pinned-url"), ("old-url", 100))
            with ThreadPoolExecutor(max_workers=1) as executor:
                first = executor.submit(first_refresh)
                try:
                    self.assertTrue(paused.wait(3))
                    second = client._resolve_for_dataset("pinned-url", refresh=True)
                finally:
                    resume.set()
                self.assertEqual(first.result(timeout=3), ("new-url", 100))
                self.assertEqual(second, ("new-url", 100))
            self.assertEqual(client._hf_client.resolve_cdn_info.call_count, 2)

    def test_debug_logging_works_with_an_existing_root_handler(self):
        output = io.StringIO()
        root = logging.getLogger()
        with patch.object(root, "handlers", [logging.NullHandler()]), \
                patch.object(root, "level", logging.WARNING), \
                patch("sys.stdout", output), \
                patch.object(DuckDBClient, "_initialize_connection"), \
                patch.object(DuckDBClient, "_load_dataset_version"):
            client = DuckDBClient(
                log_level=logging.DEBUG, config=Configuration(cache_enabled=False)
            )
            client.logger.debug("client debug marker")
            self.assertEqual(root.level, logging.WARNING)

        self.assertIn("client debug marker", output.getvalue())

    def test_clients_with_different_log_levels_do_not_change_each_other(self):
        output = io.StringIO()
        with patch("sys.stdout", output), \
                patch.object(DuckDBClient, "_initialize_connection"), \
                patch.object(DuckDBClient, "_load_dataset_version"):
            debug_client = DuckDBClient(
                log_level=logging.DEBUG, config=Configuration(cache_enabled=False)
            )
            warning_client = DuckDBClient(
                log_level=logging.WARNING, config=Configuration(cache_enabled=False)
            )
            debug_client.logger.debug("debug client marker")
            warning_client.logger.debug("warning client marker")

        self.assertIn("debug client marker", output.getvalue())
        self.assertNotIn("warning client marker", output.getvalue())


    def test_prepared_parquet_index_avoids_query_time_metadata_scan(self):
        url = (
            "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/"
            "resolve/main/data/US/stock_prices.parquet"
        )
        rows = [(0, "symbol", "AAPL", "AAPL", 4, 100)]
        fs = SimpleNamespace(
            register=Mock(return_value="defeatbeta://stock_prices"),
            prefetch_ranges=Mock(),
        )
        client = object.__new__(DuckDBClient)
        client._dataset_fs = fs
        client._parquet_indexes = {"defeatbeta://stock_prices": rows}
        client._get_cursor = Mock(side_effect=AssertionError("metadata scan during query"))
        client.logger = logging.getLogger("test")

        rewritten = client._to_dataset_sql(f"SELECT * FROM '{url}' WHERE symbol = 'AAPL'")

        self.assertIn("defeatbeta://stock_prices", rewritten)
        fs.prefetch_ranges.assert_called_once_with("defeatbeta://stock_prices", [(4, 104)])

    def test_parquet_index_is_built_in_memory_after_footer_preparation(self):
        rows = [(0, "symbol", "AAPL", "AAPL", 4, 100)]
        fs = SimpleNamespace(
            register=Mock(return_value="defeatbeta://stock_prices"),
            prepare_footer=Mock(return_value=4096),
            cached_footer_bytes=Mock(return_value=FAKE_FOOTER_BYTES),
        )
        cursor = Mock()
        cursor.execute.return_value.fetchall.return_value = rows

        @contextmanager
        def get_cursor():
            yield cursor

        client = object.__new__(DuckDBClient)
        client._dataset_fs = fs
        client._parquet_indexes = {}
        client._get_cursor = get_cursor

        self.assertEqual(client._load_or_build_parquet_index("pinned-url"), rows)
        fs.prepare_footer.assert_called_once_with("defeatbeta://stock_prices")
        cursor.execute.assert_called_once()
        self.assertEqual(client._parquet_indexes["defeatbeta://stock_prices"], rows)

    def test_project_cache_defaults_are_bounded(self):
        config = Configuration(duckdb_threads=8)
        self.assertEqual(config.cache_data_memory_limit_bytes, 64 * 1024 * 1024)
        self.assertEqual(config.cache_data_disk_limit_bytes, 5 * 1024 * 1024 * 1024)
        self.assertEqual(config.cache_fetch_workers, 16)
        self.assertFalse(hasattr(config, "cache_block_size"))
        self.assertFalse(hasattr(config, "cache_max_memory_blocks"))
        self.assertEqual(
            inspect.signature(DatasetCacheFileSystem.__init__).parameters["max_disk_bytes"].default,
            config.cache_data_disk_limit_bytes,
        )
        self.assertFalse(hasattr(config, "cache_layout"))
        self.assertTrue(config.cache_symbol_column_chunk_prefetch)

    def test_configuration_exposes_layer_specific_names(self):
        config = Configuration(
            duckdb_http_timeout_seconds=45,
            cache_http_timeout_seconds=90,
            cache_fetch_workers=3,
            cache_range_split_bytes=0,
        )
        self.assertEqual(config.duckdb_http_timeout_seconds, 45)
        self.assertEqual(config.cache_http_timeout_seconds, 90)
        self.assertEqual(config.cache_fetch_workers, 3)
        self.assertEqual(config.cache_range_split_bytes, 0)
        self.assertFalse(hasattr(config, "cache_network_connections"))
        self.assertIn("SET GLOBAL http_timeout = 45", config.get_duckdb_settings())
        with self.assertRaises(TypeError):
            Configuration(cache_network_connections=2)
        with self.assertRaises(TypeError):
            Configuration(threads=8)

    def test_cache_transport_limits_reject_invalid_values(self):
        for settings in (
            {"cache_fetch_workers": 0},
            {"cache_range_split_bytes": -1},
            {"cache_http_timeout_seconds": 0},
            {"duckdb_http_timeout_seconds": 0},
        ):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                Configuration(**settings)

    def test_configuration_documentation_matches_defaults(self):
        document = (Path(__file__).resolve().parents[1] / "doc/api/Advanced_Usage.md")
        rows = {}
        for line in document.read_text(encoding="utf-8").splitlines():
            fields = [field.strip() for field in line.split("|")]
            if len(fields) >= 5:
                rows[fields[1]] = fields[3]
        parameters = inspect.signature(Configuration).parameters
        for name, parameter in parameters.items():
            with self.subTest(name=name):
                self.assertIn(name, rows)
                documented = rows[name].strip("'\"")
                self.assertEqual(documented, str(parameter.default))

    def test_column_prefetch_can_be_disabled_without_skipping_footer(self):
        url = (
            "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/"
            "resolve/main/data/US/stock_prices.parquet"
        )
        fs = SimpleNamespace(
            register=Mock(return_value="defeatbeta://stock_prices.parquet"),
            prepare_footer=Mock(),
            prefetch_ranges=Mock(),
        )
        client = object.__new__(DuckDBClient)
        client._dataset_fs = fs
        client._parquet_indexes = {}
        client._get_cursor = Mock(side_effect=AssertionError("unneeded index"))
        client.config = Configuration(cache_symbol_column_chunk_prefetch=False)
        client.logger = logging.getLogger("test")

        rewritten = client._to_dataset_sql(
            f"SELECT * FROM '{url}' WHERE symbol = 'AAPL'"
        )

        self.assertIn("defeatbeta://stock_prices.parquet", rewritten)
        fs.prepare_footer.assert_called_once()
        client._get_cursor.assert_not_called()
        fs.prefetch_ranges.assert_not_called()

    def test_cache_layout_selection_is_not_available(self):
        with self.assertRaises(TypeError):
            Configuration(cache_layout="block")

    def test_first_symbol_query_prepares_only_its_file_and_reuses_index(self):
        price_url = (
            "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/"
            "resolve/main/data/US/stock_prices.parquet"
        )
        news_url = price_url.replace("stock_prices.parquet", "stock_news.parquet")
        rows = [(0, "symbol", "AAPL", "ZTS", 4, 100)]
        fs = SimpleNamespace(
            register=Mock(side_effect=lambda url: "defeatbeta://" + url.rsplit("/", 1)[-1]),
            prepare_footer=Mock(return_value=4096),
            cached_footer_bytes=Mock(return_value=FAKE_FOOTER_BYTES),
            prefetch_ranges=Mock(),
        )
        client = object.__new__(DuckDBClient)
        client._dataset_fs = fs
        client._parquet_indexes = {}
        client._get_cursor, cursor = metadata_cursor(rows)
        client.config = Configuration()
        client.logger = logging.getLogger("test")

        client._to_dataset_sql(f"SELECT * FROM '{price_url}' WHERE symbol = 'AAPL'")
        client._to_dataset_sql(f"SELECT * FROM '{price_url}' WHERE symbol = 'KDP'")
        client._to_dataset_sql(f"SELECT * FROM '{news_url}' WHERE symbol = 'ZTS'")

        self.assertEqual(fs.prepare_footer.call_count, 2)
        self.assertEqual(cursor.execute.call_count, 2)
        self.assertEqual(fs.prefetch_ranges.call_count, 3)

    def test_nonsymbol_parquet_query_prepares_footer_without_index(self):
        url = (
            "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/"
            "resolve/main/data/US/stock_prices.parquet"
        )
        fs = SimpleNamespace(
            register=Mock(return_value="defeatbeta://stock_prices.parquet"),
            prepare_footer=Mock(return_value=4096),
        )
        client = object.__new__(DuckDBClient)
        client._dataset_fs = fs
        client._parquet_indexes = {}
        client._get_cursor = Mock(side_effect=AssertionError("unneeded index"))
        client.config = Configuration()
        client.logger = logging.getLogger("test")

        client._to_dataset_sql(f"SELECT count(*) FROM '{url}'")

        fs.prepare_footer.assert_called_once_with("defeatbeta://stock_prices.parquet")
        client._get_cursor.assert_not_called()

    def test_parquet_index_is_not_reused_across_dataset_versions(self):
        url = (
            "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/"
            "resolve/main/data/US/stock_prices.parquet"
        )
        fs = SimpleNamespace(
            version="dataset-v1",
            register=Mock(side_effect=lambda url: f"defeatbeta://{fs.version}/stock_prices.parquet"),
            prepare_footer=Mock(),
            cached_footer_bytes=Mock(return_value=FAKE_FOOTER_BYTES),
            prefetch_ranges=Mock(),
        )
        client = object.__new__(DuckDBClient)
        client._dataset_fs = fs
        client._parquet_indexes = {}
        client._get_cursor, cursor = metadata_cursor(
            [(0, "symbol", "AAPL", "ZTS", 4, 100)]
        )
        client.config = Configuration()
        client.logger = logging.getLogger("test")

        client._to_dataset_sql(f"SELECT * FROM '{url}' WHERE symbol = 'AAPL'")
        fs.version = "dataset-v2"
        client._to_dataset_sql(f"SELECT * FROM '{url}' WHERE symbol = 'AAPL'")

        self.assertEqual(fs.prepare_footer.call_count, 2)
        self.assertEqual(cursor.execute.call_count, 2)

    def test_version_switch_after_registration_does_not_poison_new_index(self):
        url = (
            "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/"
            "resolve/main/data/US/stock_prices.parquet"
        )
        fs = SimpleNamespace(version="dataset-v1")
        calls = []

        def register(pinned_url):
            path = f"defeatbeta://{fs.version}/stock_prices.parquet"
            calls.append(path)
            if len(calls) == 1:
                fs.version = "dataset-v2"
            return path

        fs.register = register
        fs.prepare_footer = Mock()
        fs.cached_footer_bytes = Mock(return_value=FAKE_FOOTER_BYTES)
        fs.prefetch_ranges = Mock()
        client = object.__new__(DuckDBClient)
        client._dataset_fs = fs
        client._parquet_indexes = {}
        client._get_cursor, cursor = metadata_cursor(
            [(0, "symbol", "AAPL", "ZTS", 4, 100)]
        )
        client.config = Configuration()
        client.logger = logging.getLogger("test")

        client._to_dataset_sql(f"SELECT * FROM '{url}' WHERE symbol = 'AAPL'")
        client._to_dataset_sql(f"SELECT * FROM '{url}' WHERE symbol = 'KDP'")

        self.assertEqual(fs.prepare_footer.call_count, 2)
        self.assertEqual(cursor.execute.call_count, 2)

    def test_concurrent_symbol_queries_build_one_parquet_index(self):
        rows = [(0, "symbol", "AAPL", "ZTS", 4, 100)]

        fs = SimpleNamespace(
            version="dataset-v1",
            register=Mock(return_value="defeatbeta://stock_prices.parquet"),
            prepare_footer=Mock(),
            cached_footer_bytes=Mock(return_value=FAKE_FOOTER_BYTES),
        )
        client = object.__new__(DuckDBClient)
        client._dataset_fs = fs
        client._parquet_indexes = {}
        client._get_cursor, cursor = metadata_cursor(rows, delay=0.02)
        client._parquet_index_locks = {}
        client._parquet_index_locks_guard = Lock()
        client._prepared_footers = set()

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(client._load_or_build_parquet_index,
                                        ["pinned-url"] * 8))

        self.assertEqual(results, [rows] * 8)
        fs.prepare_footer.assert_called_once()
        cursor.execute.assert_called_once()

    def test_footer_preparation_failure_retains_demand_reader(self):
        url = (
            "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/"
            "resolve/main/data/US/stock_prices.parquet"
        )
        fs = SimpleNamespace(
            register=Mock(return_value="defeatbeta://stock_prices.parquet"),
            prepare_footer=Mock(side_effect=RuntimeError("temporary failure")),
        )
        client = object.__new__(DuckDBClient)
        client._dataset_fs = fs
        client._parquet_indexes = {}
        client.config = Configuration()
        client.logger = logging.getLogger("test")

        with self.assertLogs(client.logger, level="WARNING"):
            rewritten = client._to_dataset_sql(f"SELECT count(*) FROM '{url}'")

        self.assertIn("defeatbeta://stock_prices.parquet", rewritten)

    def test_metadata_timing_excludes_prefetch_scheduling(self):
        url = (
            "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/"
            "resolve/main/data/US/stock_prices.parquet"
        )
        fs = SimpleNamespace(
            register=Mock(return_value="defeatbeta://stock_prices.parquet"),
            prefetch_ranges=Mock(side_effect=lambda path, ranges: time.sleep(0.03)),
        )
        client = object.__new__(DuckDBClient)
        client._dataset_fs = fs
        client._parquet_indexes = {
            "defeatbeta://stock_prices.parquet": [(0, "symbol", "AAPL", "AAPL", 4, 100)]
        }
        client.config = Configuration()
        client.logger = logging.getLogger("test")
        events = []

        with capture_performance(events.append):
            client._to_dataset_sql(f"SELECT * FROM '{url}' WHERE symbol = 'AAPL'")

        timings = {event["name"]: event["duration_ns"] for event in events}
        self.assertIn("duckdb.prefetch_ranges", timings)
        self.assertLess(timings["duckdb.prepare_parquet_metadata"], 20_000_000)
        self.assertGreater(timings["duckdb.prefetch_ranges"], 25_000_000)

class TestDuckDBClientIntegration(unittest.TestCase):
    def test_query(self):
        with tempfile.TemporaryDirectory() as cache_directory:
            client = DuckDBClient(
                http_proxy=os.getenv("DEFEATBETA_TEST_HTTP_PROXY"),
                log_level=logging.WARNING,
                config=Configuration(duckdb_threads=8, cache_directory=cache_directory),
            )
            try:
                result = client.query(
                    "SELECT * FROM 'https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/resolve/main/data/US/stock_prices.parquet' WHERE symbol = 'BABA'"
                )
                self.assertFalse(result.empty)
                result = client.query(
                    "SELECT symbol,fiscal_year,fiscal_quarter,report_date,unnest(transcripts).paragraph_number as paragraph_number,unnest(transcripts).speaker as speaker,unnest(transcripts).content as content from 'https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/resolve/main/data/US/stock_earning_call_transcripts.parquet' where symbol='BABA' and fiscal_year=2025 and fiscal_quarter=2;"
                )
                self.assertFalse(result.empty)
                self.assertGreater(client._dataset_fs.metrics()["range_requests"], 0)
                self.assertFalse(list(Path(cache_directory).glob("*-size.json")))
                self.assertFalse(list(Path(cache_directory).glob("*-index.json")))
            finally:
                client.close()
