"""Unit tests for resolve-once CDN routing and fallback behavior."""

import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

import pandas as pd

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
    def test_default_path_enables_resolve_and_keeps_cache(self):
        config = Configuration()
        settings = config.get_duckdb_settings()
        self.assertTrue(config.resolve_direct)
        self.assertIn("LOAD cache_httpfs", settings)
        self.assertTrue(any("http_keep_alive = True" in s for s in settings))
        self.assertTrue(any("allow_asterisks_in_http_paths = true" in s for s in settings))

    def test_resolve_direct_keeps_cache_httpfs_settings(self):
        settings = Configuration(resolve_direct=True).get_duckdb_settings()
        self.assertIn("LOAD cache_httpfs", settings)
        self.assertTrue(any("cache_httpfs_cache_directory" in s for s in settings))

    def test_custom_cache_directory_is_applied(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Configuration(cache_httpfs_cache_directory=directory)
            settings = config.get_duckdb_settings()

        self.assertTrue(any(directory in setting for setting in settings))


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
        self.assertEqual(client._resolve_one(PINNED), PINNED)


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
        client.resolve_direct = True
        client._cdn_lock = Lock()
        client._cdn_cache = {PINNED: (CDN, 1.0)}
        client._to_cdn_sql = lambda sql: rewrite_resolve_urls(sql, lambda url: CDN)

        original = f"SELECT * FROM '{PINNED}'"
        result = client.query(original)

        self.assertEqual(result.to_dict("records"), [{"value": 1}])
        self.assertEqual(calls, [f"SELECT * FROM read_parquet(['{CDN}'])", original])
        self.assertNotIn(PINNED, client._cdn_cache)


class TestClientRegistry(unittest.TestCase):
    def test_different_configurations_do_not_share_a_client(self):
        from defeatbeta_api.client import duckdb_client as module

        created = []

        def make_client(http_proxy, log_level, config):
            client = SimpleNamespace(connection=object(), config=config)
            created.append(client)
            return client

        with patch.object(module, "DuckDBClient", side_effect=make_client), \
                patch.object(module, "_instances", {}):
                direct = module.get_duckdb_client(config=Configuration(resolve_direct=True))
                cached = module.get_duckdb_client(config=Configuration(resolve_direct=False))
                direct_again = module.get_duckdb_client(config=Configuration(resolve_direct=True))

        self.assertIsNot(direct, cached)
        self.assertIs(direct, direct_again)
        self.assertEqual(len(created), 2)


class TestHuggingFaceResolver(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
