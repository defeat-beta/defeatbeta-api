import logging
import inspect
import io
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
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
        config = Configuration(threads=8)
        self.assertEqual(config.cache_max_memory_bytes, 64 * 1024 * 1024)
        self.assertEqual(config.cache_max_disk_bytes, 5 * 1024 * 1024 * 1024)
        self.assertEqual(config.cache_workers, 3)
        self.assertFalse(hasattr(config, "cache_block_size"))
        self.assertFalse(hasattr(config, "cache_max_memory_blocks"))
        self.assertEqual(
            inspect.signature(DatasetCacheFileSystem.__init__).parameters["max_disk_bytes"].default,
            config.cache_max_disk_bytes,
        )
        self.assertFalse(hasattr(config, "cache_layout"))
        self.assertTrue(config.cache_column_prefetch)

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
        client.config = Configuration(cache_column_prefetch=False)
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
                config=Configuration(threads=8, cache_directory=cache_directory),
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
