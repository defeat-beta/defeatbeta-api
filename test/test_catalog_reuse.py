"""Verify parsed company metadata and version reuse without remote services."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event, Lock
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import duckdb
import pandas as pd
from pandas.testing import assert_frame_equal

from defeatbeta_api.client.dataset_cache_fs import DatasetVersionChanged
from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.client.shared_resources import SharedCache
from defeatbeta_api.data.company_meta import CompanyMeta
from defeatbeta_api.data.sql.sql_loader import load_sql
from defeatbeta_api.data.ticker import Ticker
from test import test_duckdb_client as client_fixtures


class TestCatalogReuse(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.client = client_fixtures.TestDuckDBClient().resolution_client()
        self.client.connection = duckdb.connect(config={"threads": 4})
        self.addCleanup(self.client.connection.close)
        self.client.logger = Mock()
        self.client.config = Configuration(cache_version_check_interval_seconds=300)
        self.client._dataset_generation = 0
        self.client._catalog_cache = SharedCache()
        self.client._last_version_check = time.monotonic()
        self.client._hf_client.get_shared_data_update_time.return_value = self.client._data_update_time
        self.client._hf_client.session = Mock()
        self.sources = {}
        self.calls = []
        self.calls_lock = Lock()
        self.write_catalog("US", [
            {"cik_str": 1, "ticker": "AAPL", "title": "Apple", "financial_currency": "USD"},
            {"cik_str": None, "ticker": "ZZZ", "title": "Example", "financial_currency": None},
        ])
        self.write_catalog("HK", [
            {"isin": "KYG875721634", "ticker": "0700.HK", "title": "TENCENT", "financial_currency": "CNY"},
        ])
        self.client.query = Mock(side_effect=self.query)
        factory = patch("defeatbeta_api.data.company_meta.get_duckdb_client", return_value=self.client)
        factory.start()
        self.addCleanup(factory.stop)
        self.us = self.company("US")
        self.hk = self.company("HK")

    def company(self, market):
        return CompanyMeta(market=market)

    def write_catalog(self, market, companies):
        path = Path(self.directory.name) / f"{market}-{time.monotonic_ns()}.json"
        path.write_text(json.dumps({"data": {str(i): row for i, row in enumerate(companies)}}))
        self.sources[CompanyMeta._MARKETS[market]["url"]] = path

    def local_query(self, sql):
        for url, path in self.sources.items():
            sql = sql.replace(url, str(path).replace("'", "''"))
        with self.client._get_cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchdf()

    def query(self, sql):
        with self.calls_lock:
            self.calls.append(sql)
        return self.local_query(sql)

    def refresh(self, version=None, footer_index=None):
        self.client._hf_client.get_shared_data_update_time.return_value = (
            version or self.client._data_update_time)
        self.client._hf_client.dataset_spec = {"footer_index": footer_index or {}}
        self.client._last_version_check = float("-inf")
        self.client._refresh_dataset_version_if_due()

    def test_catalog_is_loaded_once_across_instances_and_public_methods(self):
        other = self.company("US")
        self.assertEqual(self.us.get_company_info("AAPL")["name"], "Apple")
        self.assertEqual(other.get_all_tickers(), ["AAPL", "ZZZ"])
        currencies = other.get_financial_currency_map()
        self.assertEqual(currencies["AAPL"], "USD")
        self.assertTrue(pd.isna(currencies["ZZZ"]))
        self.assertEqual(len(self.us.get_all_companies_info()), 2)
        self.assertEqual(len(self.calls), 1)
        self.client._hf_client.get_shared_data_update_time.assert_not_called()

    def test_symbol_selection_preserves_sql_values_dtypes_and_empty_results(self):
        for company, symbols in ((self.us, ("AAPL", "ZZZ", "MISSING")),
                                  (self.hk, ("0700.HK", "MISSING"))):
            for symbol in symbols:
                with self.subTest(market=company.market, symbol=symbol):
                    sql = load_sql("select_company_by_symbol", url=company.company_tickers_url,
                        symbol=symbol, identifier_field=company._identifier_field,
                        identifier_type=company._identifier_type, identifier_alias=company._identifier_alias)
                    assert_frame_equal(company._get_company_by_symbol(symbol),
                                       self.local_query(sql), check_exact=True)
        self.assertIsNone(self.us.get_company_info("MISSING"))

    def test_returned_values_do_not_mutate_the_shared_catalog(self):
        frame = self.us._get_all_companies()
        frame.loc[0, "name"] = "Changed"
        frame.drop(index=1, inplace=True)
        rows = self.us.get_all_companies_info()
        rows[0]["name"] = "Also changed"
        currencies = self.us.get_financial_currency_map()
        currencies["AAPL"] = "EUR"
        self.assertEqual(self.us.get_company_info("AAPL")["name"], "Apple")
        self.assertEqual(self.us.get_financial_currency_map()["AAPL"], "USD")
        self.assertEqual(len(self.us.get_all_tickers()), 2)
        self.assertEqual(len(self.calls), 1)

    def test_markets_have_independent_schemas_and_catalogs(self):
        us, hk = self.us.get_company_info("AAPL"), self.hk.get_company_info("0700.HK")
        self.assertEqual(us["cik"], 1)
        self.assertEqual(hk["isin"], "KYG875721634")
        self.assertNotIn("isin", us)
        self.assertNotIn("cik", hk)
        self.assertEqual(len(self.calls), 2)

    def test_version_and_same_version_metadata_changes_invalidate_catalog(self):
        self.assertEqual(self.us.get_company_info("AAPL")["name"], "Apple")
        for version, metadata in (("2026-10-13T00:00:00Z", {}),
                                  ("2026-10-13T00:00:00Z", {"US/company_tickers.json": {"file_size": 123}})):
            with self.subTest(version=version, metadata=metadata):
                name = f"Revision {len(self.calls)}"
                self.write_catalog("US", [{"cik_str": 1, "ticker": "AAPL", "title": name,
                                           "financial_currency": "USD"}])
                self.refresh(version, metadata)
                self.assertEqual(self.us.get_company_info("AAPL")["name"], name)
        self.assertEqual(len(self.calls), 3)

    def test_concurrent_catalog_loads_share_one_query(self):
        barrier = Barrier(16)

        def read(_):
            barrier.wait(timeout=10)
            return self.company("US").get_company_info("AAPL")

        with ThreadPoolExecutor(max_workers=16) as executor:
            rows = list(executor.map(read, range(16)))
        self.assertEqual([row["name"] for row in rows], ["Apple"] * 16)
        self.assertEqual(len(self.calls), 1)

    def test_concurrent_market_filters_keep_cursor_registrations_isolated(self):
        barrier = Barrier(16)

        def read(index):
            barrier.wait(timeout=10)
            company, symbol = (self.us, "AAPL") if index % 2 == 0 else (self.hk, "0700.HK")
            return company.get_company_info(symbol)

        with ThreadPoolExecutor(max_workers=16) as executor:
            rows = list(executor.map(read, range(16)))
        for index, row in enumerate(rows):
            self.assertEqual(row["symbol"], "AAPL" if index % 2 == 0 else "0700.HK")
            self.assertIn("cik" if index % 2 == 0 else "isin", row)
        self.assertEqual(len(self.calls), 2)

    def test_empty_catalog_is_reused_and_missing_symbols_remain_absent(self):
        self.write_catalog("US", [])
        self.assertEqual(self.us.get_all_tickers(), [])
        self.assertEqual(self.us.get_financial_currency_map(), {})
        self.assertIsNone(self.us.get_company_info("MISSING"))
        self.assertEqual(len(self.calls), 1)

    def test_inflight_catalog_is_retried_after_a_version_change(self):
        entered, release = Event(), Event()

        def delayed(sql):
            frame = self.query(sql)
            if not entered.is_set():
                entered.set()
                if not release.wait(5):
                    raise TimeoutError("Catalog query was not released")
            return frame

        self.client.query.side_effect = delayed
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(self.us.get_company_info, "AAPL")
            try:
                self.assertTrue(entered.wait(3))
                self.write_catalog("US", [{"cik_str": 1, "ticker": "AAPL", "title": "New",
                                          "financial_currency": "USD"}])
                self.refresh("2026-10-13T00:00:00Z")
            finally:
                release.set()
            self.assertEqual(pending.result(timeout=3)["name"], "New")
        self.assertEqual(self.us.get_company_info("AAPL")["name"], "New")
        self.assertEqual(len(self.calls), 2)

    def test_failed_catalog_build_can_be_retried(self):
        self.client.query.side_effect = [RuntimeError("Temporary catalog failure"), self.local_query(
            load_sql("select_all_companies", url=self.us.company_tickers_url,
                     identifier_field="cik_str", identifier_type="INTEGER", identifier_alias="cik"))]
        with self.assertRaisesRegex(RuntimeError, "Temporary catalog failure"):
            self.us.get_all_tickers()
        self.assertEqual(self.us.get_all_tickers(), ["AAPL", "ZZZ"])
        self.assertEqual(self.us.get_all_tickers(), ["AAPL", "ZZZ"])
        self.assertEqual(self.client.query.call_count, 2)

    def test_cache_disabled_keeps_fresh_catalog_reads(self):
        self.client.config.cache_enabled = False
        self.us.get_all_tickers()
        self.us.get_all_tickers()
        self.assertEqual(len(self.calls), 2)

    def test_repeated_version_changes_stop_after_two_catalog_attempts(self):
        frame = self.local_query(load_sql("select_all_companies", url=self.us.company_tickers_url,
            identifier_field="cik_str", identifier_type="INTEGER", identifier_alias="cik"))

        def changed(sql):
            self.client._dataset_generation += 1
            return frame

        self.client.query.side_effect = changed
        with self.assertRaises(DatasetVersionChanged):
            self.us.get_all_tickers()
        self.assertEqual(self.client.query.call_count, 2)

    def test_beta_uses_the_active_client_version_without_fresh_metadata_requests(self):
        dates = pd.date_range(end="2026-10-12", periods=400)
        prices = pd.DataFrame({"report_date": dates.strftime("%Y-%m-%d"),
                               "stock_close": range(100, 500), "benchmark_close": range(200, 600)})
        ticker = Ticker.__new__(Ticker)
        ticker.ticker = "AAPL"
        ticker.duckdb_client = self.client
        ticker.huggingface_client = SimpleNamespace(
            get_data_update_time=Mock(side_effect=AssertionError("Redundant fresh metadata request")),
            get_url_path=lambda table: "unused.parquet")
        self.client.query.side_effect = lambda sql: prices.copy()
        for version in ("2026-10-12T00:00:00Z", "2026-10-12 00:00:00"):
            self.client._data_update_time = version
            result = ticker.beta("1y")
            self.assertEqual(result.iloc[0]["report_date"], "2026-10-12")
        self.client._hf_client.get_shared_data_update_time.assert_not_called()

    def test_active_version_still_refreshes_when_the_interval_expires(self):
        self.assertEqual(self.client._get_data_update_time(), self.client._data_update_time)
        self.client._hf_client.get_shared_data_update_time.assert_not_called()
        self.client._hf_client.get_shared_data_update_time.return_value = "2026-10-13T00:00:00Z"
        self.client._last_version_check = float("-inf")
        self.assertEqual(self.client._get_data_update_time(), "2026-10-13T00:00:00Z")
        self.assertEqual(self.client._dataset_generation, 1)

    def test_zero_interval_checks_the_version_on_every_call(self):
        self.client.config.cache_version_check_interval_seconds = 0
        self.client._hf_client.get_shared_data_update_time.side_effect = [
            "2026-10-12T00:00:00Z", "2026-10-13T00:00:00Z"]
        self.assertEqual(self.client._get_data_update_time(), "2026-10-12T00:00:00Z")
        self.assertEqual(self.client._get_data_update_time(), "2026-10-13T00:00:00Z")
        self.assertEqual(self.client._hf_client.get_shared_data_update_time.call_count, 2)

    def test_closed_client_does_not_serve_a_cached_catalog(self):
        self.us.get_all_tickers()
        self.client.close()
        self.assertIsNone(self.client._catalog_cache)
        with self.assertRaises(AttributeError):
            self.us.get_all_tickers()


if __name__ == "__main__":
    unittest.main()
