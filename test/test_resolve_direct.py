"""Unit tests for resolve-once CDN routing and fallback behavior."""

import io
import unittest
import tempfile
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

import pandas as pd
import defeatbeta_api

from defeatbeta_api.client.duckdb_client import (
    DuckDBClient,
    capture_performance,
    redact_signed_urls,
    rewrite_resolve_urls,
)
from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.client.hugging_face_client import HuggingFaceClient


PINNED = ("https://huggingface.co/datasets/defeatbeta/yahoo-finance-data"
          "/resolve/main/data/US/stock_prices.parquet")
CDN = ("https://us.aws.cdn.hf.co/xet-bridge-us/abc/stock_prices.parquet"
       "?Expires=1&Signature=secret")
JSON = ("https://huggingface.co/datasets/defeatbeta/yahoo-finance-data"
        "/resolve/main/data/US/company_tickers.json")


class TestWelcome(unittest.TestCase):
    def test_welcome_supports_cp1252_stdout(self):
        output = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        with patch.object(defeatbeta_api, "_welcome_printed", False), \
             patch("sys.stdout", output):
            defeatbeta_api._print_welcome("2026-09-29")
            output.flush()
            rendered = output.buffer.getvalue().decode("cp1252")

        self.assertIn("2026-09-29", rendered)
        self.assertIn(defeatbeta_api.__version__, rendered)
        self.assertIn("*:: Data Update Time ::", rendered)

    def test_welcome_keeps_icon_on_utf8_stdout(self):
        output = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        with patch.object(defeatbeta_api, "_welcome_printed", False), \
             patch("sys.stdout", output):
            defeatbeta_api._print_welcome("2026-09-29")
            output.flush()
            rendered = output.buffer.getvalue().decode("utf-8")

        self.assertIn("📈:: Data Update Time ::", rendered)


class TestRewrite(unittest.TestCase):
    def test_rewrites_from_sites_with_reader(self):
        sql = f"SELECT * FROM '{PINNED}' WHERE symbol = 'AAPL'"
        out = rewrite_resolve_urls(sql, lambda url: CDN)
        self.assertEqual(out, f"SELECT * FROM read_parquet(['{CDN}']) WHERE symbol = 'AAPL'")

    def test_rewrites_join_with_alias(self):
        sql = (f"SELECT p1.report_date FROM '{PINNED}' p1 "
               f"INNER JOIN '{PINNED}' p2 ON p1.report_date = p2.report_date")
        out = rewrite_resolve_urls(sql, lambda url: CDN)
        self.assertEqual(out, (f"SELECT p1.report_date FROM read_parquet(['{CDN}']) p1 "
                               f"INNER JOIN read_parquet(['{CDN}']) p2 ON p1.report_date = p2.report_date"))

    def test_rewrites_explicit_parquet_reader_as_exact_file_list(self):
        sql = f"SELECT * FROM read_parquet('{PINNED}')"
        out = rewrite_resolve_urls(sql, lambda url: CDN)
        self.assertEqual(out, f"SELECT * FROM read_parquet(['{CDN}'])")

    def test_leaves_json_reader_on_pinned_url(self):
        resolve = Mock(return_value="https://huggingface.co/api/resolve-cache/file.json?etag=abc")
        sql = f"SELECT * FROM read_json('{JSON}')"
        self.assertEqual(rewrite_resolve_urls(sql, resolve), sql)
        resolve.assert_not_called()

    def test_keeps_original_on_resolver_failure(self):
        sql = f"SELECT * FROM '{PINNED}'"
        out = rewrite_resolve_urls(sql, lambda url: (_ for _ in ()).throw(IOError("down")))
        self.assertEqual(out, sql)

    def test_leaves_other_sql_alone(self):
        sql = "SELECT 1"
        self.assertEqual(rewrite_resolve_urls(sql, lambda url: CDN), sql)

    def test_redacts_signatures(self):
        self.assertEqual(
            redact_signed_urls(f"FROM '{CDN}'"),
            "FROM 'https://us.aws.cdn.hf.co/xet-bridge-us/abc/stock_prices.parquet?<redacted>'",
        )
        alternate_cdn = "https://cdn-lfs-us-1.hf.co/repos/abc/file?Expires=1&Signature=secret"
        self.assertEqual(
            redact_signed_urls(alternate_cdn),
            "https://cdn-lfs-us-1.hf.co/repos/abc/file?<redacted>",
        )
        self.assertEqual(redact_signed_urls("no urls here"), "no urls here")


class TestConfiguration(unittest.TestCase):
    def test_default_path_uses_project_cache_without_community_extension(self):
        config = Configuration()
        settings = config.get_duckdb_settings()
        self.assertTrue(config.cache_enabled)
        self.assertFalse(any("cache_httpfs" in setting for setting in settings))
        self.assertLess(settings.index("INSTALL httpfs"), settings.index("LOAD httpfs"))
        self.assertTrue(any("http_keep_alive = True" in s for s in settings))

    def test_old_extension_settings_are_not_public_configuration(self):
        with self.assertRaises(TypeError):
            Configuration(cache_httpfs_cache_block_size=1024)

    def test_custom_cache_directory_is_applied(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Configuration(cache_directory=directory)
            self.assertEqual(config.get_cache_directory(), str(Path(directory).resolve()))

    def test_default_cache_directory_does_not_reuse_extension_files(self):
        self.assertIn("dataset-cache", Path(Configuration().get_cache_directory()).parts)

    def test_cache_limits_use_project_keys(self):
        config = Configuration(cache_data_memory_limit_bytes=2048)
        self.assertEqual(config.cache_data_memory_limit_bytes, 2048)

    def test_negative_cache_version_check_interval_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "version check interval"):
            Configuration(cache_version_check_interval_seconds=-1)


class TestPerformanceCapture(unittest.TestCase):
    class _Cursor:
        def sql(self, sql):
            result = Mock()
            result.df.return_value = pd.DataFrame([{"value": 1}])
            return result

        def close(self):
            pass

    class _Connection:
        def cursor(self):
            return TestPerformanceCapture._Cursor()

    def test_execute_query_emits_precise_phase_timings(self):
        import logging

        client = DuckDBClient.__new__(DuckDBClient)
        client.connection = self._Connection()
        client.logger = logging.getLogger("test")
        events = []

        with capture_performance(events.append):
            result = client._execute_query("SELECT 1")

        self.assertEqual(result.to_dict("records"), [{"value": 1}])
        names = [event["name"] for event in events]
        self.assertEqual(
            names,
            [
                "duckdb.cursor.open",
                "duckdb.sql_to_dataframe",
                "duckdb.cursor.close",
                "duckdb.execute_query",
            ],
        )
        self.assertTrue(all(event["duration_ns"] >= 0 for event in events))
        self.assertEqual(events[-1]["rows"], 1)


class TestMemo(unittest.TestCase):
    def _client(self):
        client = DuckDBClient.__new__(DuckDBClient)
        import logging
        from threading import Lock
        client.logger = logging.getLogger("test")
        client._cdn_cache = {}
        client._cdn_lock = Lock()
        client._resolve_ttl = 1800
        client.http_proxy = None
        return client

    def test_memoizes_within_ttl(self):
        client = self._client()
        calls = []

        class FakeHF:
            def resolve_cdn_url(self, url, proxies=None, timeout=20):
                calls.append(url)
                return CDN

        client._hf_client = FakeHF()
        first = client._resolve_one(PINNED)
        second = client._resolve_one(PINNED)
        self.assertEqual(first, CDN)
        self.assertEqual(second, CDN)
        self.assertEqual(len(calls), 1)

    def test_falls_back_to_pinned_url(self):
        client = self._client()

        class FailingHF:
            def resolve_cdn_url(self, url, proxies=None, timeout=20):
                raise RuntimeError("boom")

        client._hf_client = FailingHF()
        with self.assertLogs(client.logger, level="WARNING") as logs:
            self.assertEqual(client._resolve_one(PINNED), PINNED)
        self.assertIn("CDN resolve failed", logs.output[0])


class TestQueryFallback(unittest.TestCase):
    class _Cursor:
        def __init__(self, calls):
            self.calls = calls

        def sql(self, sql):
            self.calls.append(sql)
            if "us.aws.cdn.hf.co" in sql:
                raise OSError("CDN blocked")
            result = Mock()
            result.df.return_value = pd.DataFrame([{"value": 1}])
            return result

        def close(self):
            pass

    class _Connection:
        def __init__(self, calls):
            self.calls = calls

        def cursor(self):
            return TestQueryFallback._Cursor(self.calls)

    def test_cdn_query_failure_retries_original_sql_and_invalidates_url(self):
        import logging
        from threading import Lock

        calls = []
        client = DuckDBClient.__new__(DuckDBClient)
        client.connection = self._Connection(calls)
        client.logger = logging.getLogger("test")
        client.resolve_cdn_for_uncached_reads = True
        client._cdn_lock = Lock()
        client._cdn_cache = {PINNED: (CDN, 1.0)}
        client._to_cdn_sql = lambda sql: rewrite_resolve_urls(sql, lambda url: CDN)

        original = f"SELECT * FROM '{PINNED}'"
        with self.assertLogs(client.logger, level="WARNING") as logs:
            result = client.query(original)

        self.assertEqual(result.to_dict("records"), [{"value": 1}])
        self.assertEqual(calls, [f"SELECT * FROM read_parquet(['{CDN}'])", original])
        self.assertNotIn(PINNED, client._cdn_cache)
        self.assertIn("CDN query failed", logs.output[0])

    def test_dataset_cache_failure_uses_existing_remote_path(self):
        import logging

        client = DuckDBClient.__new__(DuckDBClient)
        client.logger = logging.getLogger("dataset-cache-fallback-test")
        client._dataset_fs = object()
        client._refresh_dataset_version_if_due = Mock()
        client.resolve_cdn_for_uncached_reads = True
        client._to_cdn_sql = lambda sql: rewrite_resolve_urls(sql, lambda url: CDN)
        expected = pd.DataFrame([{"value": 1}])
        client._execute_query = Mock(side_effect=[RuntimeError("cache unavailable"), expected])
        sql = f"SELECT * FROM '{PINNED}'"

        with self.assertLogs(client.logger, level="WARNING") as logs:
            self.assertTrue(client.query(sql).equals(expected))
        self.assertIn("Dataset cache query failed", logs.output[0])
        client._refresh_dataset_version_if_due.assert_called_once_with()
        self.assertEqual(client._execute_query.call_args_list[0].args, (sql,))
        self.assertEqual(
            client._execute_query.call_args_list[0].kwargs,
            {"use_dataset_cache": True},
        )
        self.assertEqual(
            client._execute_query.call_args_list[1].args,
            (f"SELECT * FROM read_parquet(['{CDN}'])",),
        )


class TestClientRegistry(unittest.TestCase):
    def test_explicit_proxies_use_separate_clients(self):
        from defeatbeta_api.client import duckdb_client as module

        created = []

        def make_client(http_proxy, log_level, config):
            client = SimpleNamespace(connection=object(), http_proxy=http_proxy)
            created.append(client)
            return client

        with patch.object(module, "DuckDBClient", side_effect=make_client), \
                patch.object(module, "_instances", {}):
            first = module.get_duckdb_client(http_proxy="http://proxy-one.example:8123")
            second = module.get_duckdb_client(http_proxy="http://proxy-two.example:8123")
            first_again = module.get_duckdb_client(http_proxy="http://proxy-one.example:8123")

        self.assertIsNot(first, second)
        self.assertIs(first, first_again)
        self.assertEqual(len(created), 2)

    def test_different_configurations_do_not_share_a_client(self):
        from defeatbeta_api.client import duckdb_client as module

        created = []

        def make_client(http_proxy, log_level, config):
            client = SimpleNamespace(connection=object(), config=config)
            created.append(client)
            return client

        with patch.object(module, "DuckDBClient", side_effect=make_client), \
                patch.object(module, "_instances", {}):
                direct = module.get_duckdb_client(config=Configuration(resolve_cdn_for_uncached_reads=True))
                cached = module.get_duckdb_client(config=Configuration(resolve_cdn_for_uncached_reads=False))
                direct_again = module.get_duckdb_client(config=Configuration(resolve_cdn_for_uncached_reads=True))

        self.assertIsNot(direct, cached)
        self.assertIs(direct, direct_again)
        self.assertEqual(len(created), 2)


class TestHuggingFaceResolver(unittest.TestCase):
    def test_socks_proxy_dependencies_are_installed(self):
        self.assertIsNotNone(importlib.util.find_spec("socks"))
        self.assertIsNotNone(importlib.util.find_spec("socksio"))

    def test_duckdb_proxy_is_configured_before_loading_httpfs(self):
        connection = Mock()
        with patch(
            "defeatbeta_api.client.duckdb_client.duckdb.connect",
            return_value=connection,
        ), patch.object(DuckDBClient, "_load_dataset_version"):
            DuckDBClient(
                http_proxy="http://proxy.example:8123",
                config=Configuration(cache_enabled=False),
            )

        statements = [call.args[0] for call in connection.execute.call_args_list]
        self.assertLess(
            next(index for index, sql in enumerate(statements) if "SET GLOBAL http_proxy" in sql),
            statements.index("LOAD httpfs"),
        )

    def test_client_passes_explicit_proxy_to_spec_reader(self):
        proxy = "http://proxy.example:8123"

        with patch.object(DuckDBClient, "_initialize_connection"), \
                patch.object(DuckDBClient, "_load_dataset_version"), \
                patch("defeatbeta_api.client.duckdb_client.HuggingFaceClient") as reader:
            DuckDBClient(http_proxy=proxy, config=Configuration(cache_enabled=False))

        reader.assert_called_once_with(http_proxy=proxy)

    def test_spec_request_uses_explicit_proxy(self):
        proxy = "http://proxy.example:8123"
        client = HuggingFaceClient(http_proxy=proxy)
        spec = {
            "update_time": "2026-09-28T00:00:00Z",
            "footer_index": {"US/stock_prices.parquet": {
                "file_size": 100, "footer_size": 20,
                "footer_sha256": "a" * 64,
            }},
        }
        client.session.get = Mock(return_value=SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: spec,
        ))

        self.assertEqual(client.get_data_update_time(), "2026-09-28T00:00:00Z")
        self.assertEqual(client.dataset_spec, spec)
        self.assertEqual(client.session.get.call_args.kwargs["proxies"], {
            "http": proxy, "https": proxy,
        })

    def test_spec_request_inherits_environment_without_explicit_proxy(self):
        client = HuggingFaceClient()
        client.session.get = Mock(return_value=SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"update_time": "2026-09-28T00:00:00Z"},
        ))

        client.get_data_update_time()

        self.assertNotIn("proxies", client.session.get.call_args.kwargs)

    def test_rejects_non_https_redirects(self):
        client = HuggingFaceClient.__new__(HuggingFaceClient)
        response = SimpleNamespace(
            status_code=302,
            headers={"Location": "http://example.com/file.parquet?Signature=secret"},
        )
        client.session = Mock()
        client.session.head.return_value = response

        with self.assertRaisesRegex(RuntimeError, "Unsafe redirect"):
            client.resolve_cdn_url(PINNED)

    def test_resolve_cdn_info_uses_linked_size_without_another_request(self):
        client = HuggingFaceClient.__new__(HuggingFaceClient)
        client.session = Mock()
        client.session.head.return_value = SimpleNamespace(
            status_code=302,
            headers={"Location": CDN, "X-Linked-Size": "466437904"},
        )

        self.assertEqual(client.resolve_cdn_info(PINNED), (CDN, 466437904))
        client.session.head.assert_called_once()

    def test_resolve_cdn_info_accepts_direct_json_response(self):
        client = HuggingFaceClient.__new__(HuggingFaceClient)
        client.session = Mock()
        client.session.head.return_value = SimpleNamespace(
            status_code=200,
            headers={"Content-Length": "42"},
        )

        self.assertEqual(client.resolve_cdn_info(JSON), (JSON, 42))

    def test_resolve_cdn_info_follows_safe_relative_json_redirect(self):
        client = HuggingFaceClient.__new__(HuggingFaceClient)
        client.session = Mock()
        client.session.head.side_effect = [
            SimpleNamespace(status_code=307, headers={
                "Location": "/api/resolve-cache/datasets/defeatbeta/file.json",
            }),
            SimpleNamespace(status_code=200, headers={"Content-Length": "42"}),
        ]

        self.assertEqual(
            client.resolve_cdn_info(JSON),
            ("https://huggingface.co/api/resolve-cache/datasets/defeatbeta/file.json", 42),
        )
        self.assertEqual(client.session.head.call_count, 2)


class TestImportSideEffects(unittest.TestCase):
    def test_package_retains_hugging_face_client_export(self):
        import defeatbeta_api

        self.assertIs(defeatbeta_api.HuggingFaceClient, HuggingFaceClient)

    def test_import_does_not_access_network_or_download_nltk_data(self):
        import defeatbeta_api
        fake_nltk = Mock()

        with patch.object(HuggingFaceClient, "get_data_update_time", return_value="test") as fetch:
            with patch.dict(sys.modules, {"nltk": fake_nltk}):
                importlib.reload(defeatbeta_api)

        fetch.assert_not_called()
        fake_nltk.download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
