"""Offline regressions and opt-in live checks for US/HK price routing."""

from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
import sys
import unittest
from unittest.mock import Mock, patch

import duckdb
import pandas as pd
from pandas.testing import assert_frame_equal

from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.client.hugging_face_client import HuggingFaceClient
from defeatbeta_api.data.ticker import Ticker
from defeatbeta_api.data.tickers import Tickers
from defeatbeta_api.utils.const import stock_prices, tables
from test.client_stub import bare_client


HK_SYMBOLS = ["0700.HK", "9988.HK", "1299.HK", "2800.HK"]
COLUMNS = ["symbol", "report_date", "open", "close", "high", "low", "volume"]


class TestPriceRouting(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.connection = duckdb.connect(config={"threads": 4})
        self.addCleanup(self.connection.close)
        self.client = bare_client(connection=self.connection)
        self.urls = HuggingFaceClient()
        self.sources = {}
        for market, symbols in (("US", ["AAPL", "1234.HK"]), ("HK", HK_SYMBOLS)):
            path = Path(directory.name) / market / "stock_prices.parquet"
            path.parent.mkdir()
            self.connection.execute(
                f"CREATE TABLE prices_{market} (symbol VARCHAR, report_date VARCHAR, "
                "open DECIMAL(16,4), close DECIMAL(16,4), high DECIMAL(16,4), "
                "low DECIMAL(16,4), volume BIGINT)")
            self.connection.executemany(
                f"INSERT INTO prices_{market} VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(symbol, day, 10.125, 11.25, 12.5, 9.75, volume)
                 for symbol in symbols
                 for day, volume in (("2026-11-06", 0), ("2026-11-09", 123456))])
            self.connection.execute(
                f"COPY (SELECT * FROM prices_{market} ORDER BY symbol, report_date) "
                "TO ? (FORMAT PARQUET)", [str(path)])
            url = f"{self.urls.base_url}/resolve/main/data/{market}/stock_prices.parquet"
            self.sources[url] = path
        self.client.query = Mock(side_effect=self.local_query)
        for target in ("get_duckdb_client", "Treasure", "CompanyMeta"):
            replacement = patch(f"defeatbeta_api.data.ticker.{target}")
            mocked = replacement.start()
            self.addCleanup(replacement.stop)
            if target == "get_duckdb_client":
                mocked.return_value = self.client

    def local_query(self, sql):
        for url, path in self.sources.items():
            sql = sql.replace(url, str(path).replace("'", "''"))
        return self.client._execute_query(sql)

    def test_existing_table_urls_default_to_us(self):
        for table in tables:
            with self.subTest(table=table):
                expected = f"{self.urls.base_url}/resolve/main/data/US/{table}.parquet"
                self.assertEqual(self.urls.get_url_path(table), expected)
                self.assertEqual(self.urls.get_url_path(table, market="us"), expected)

    def test_hk_price_url_accepts_case_insensitive_market(self):
        for market in ("HK", "hk"):
            with self.subTest(market=market):
                self.assertEqual(
                    self.urls.get_url_path(stock_prices, market=market),
                    f"{self.urls.base_url}/resolve/main/data/HK/stock_prices.parquet")

    def test_unsupported_markets_are_rejected(self):
        for market in ("JP", "", None, 1):
            with self.subTest(market=market):
                with self.assertRaisesRegex(ValueError, "Unsupported market"):
                    self.urls.get_url_path(stock_prices, market=market)

    def test_hk_rejects_tables_that_are_not_published(self):
        for table in tables:
            if table != stock_prices:
                with self.subTest(table=table):
                    with self.assertRaisesRegex(ValueError, "Unsupported.*HK|HK.*supported"):
                        self.urls.get_url_path(table, market="HK")

    def test_unknown_table_is_rejected(self):
        for market in ("US", "HK"):
            with self.subTest(market=market):
                with self.assertRaisesRegex(ValueError, "Invalid table"):
                    self.urls.get_url_path("missing_table", market=market)

    def test_acceptance_symbols_read_hk_prices_with_existing_schema(self):
        for symbol in HK_SYMBOLS:
            with self.subTest(symbol=symbol):
                actual = Ticker(symbol).price()
                expected = self.connection.execute(
                    "SELECT * FROM prices_HK WHERE symbol = ? ORDER BY report_date",
                    [symbol]).fetchdf()
                assert_frame_equal(actual, expected, check_exact=True)
                self.assertEqual(list(actual.columns), COLUMNS)
                self.assertEqual(actual["symbol"].tolist(), [symbol, symbol])
                self.assertEqual(actual["volume"].tolist(), [0, 123456])

    def test_lowercase_symbol_preserves_leading_zero(self):
        ticker = Ticker("0700.hk")
        self.assertEqual(ticker.ticker, "0700.HK")
        self.assertEqual(ticker.price()["symbol"].tolist(), ["0700.HK", "0700.HK"])

    def test_us_prices_keep_the_same_values_and_types(self):
        expected = self.connection.execute(
            "SELECT * FROM prices_US WHERE symbol = 'AAPL' ORDER BY report_date").fetchdf()
        assert_frame_equal(Ticker("aapl").price(), expected, check_exact=True)

    def test_missing_hk_symbol_returns_empty_frame_without_us_fallback(self):
        result = Ticker("1234.HK").price()
        self.assertTrue(result.empty)
        self.assertEqual(list(result.columns), COLUMNS)
        self.assertIn("/data/HK/stock_prices.parquet", self.client.query.call_args.args[0])
        self.assertNotIn("/data/US/", self.client.query.call_args.args[0])

    def test_price_does_not_require_catalog_membership(self):
        ticker = Ticker("2800.HK")
        ticker.company_meta.get_company_info.side_effect = AssertionError("Unexpected catalog read")
        ticker.company_meta.get_all_tickers.side_effect = AssertionError("Unexpected catalog read")
        self.assertEqual(len(ticker.price()), 2)
        ticker.company_meta.get_company_info.assert_not_called()
        ticker.company_meta.get_all_tickers.assert_not_called()

    def test_other_table_queries_keep_their_existing_us_paths(self):
        ticker = Ticker("0700.HK")
        with patch.object(self.client, "query", return_value=pd.DataFrame()) as query:
            ticker.info()
            ticker.splits()
            ticker.dividends()
        self.assertEqual(query.call_count, 3)
        for call in query.call_args_list:
            self.assertIn("/data/US/", call.args[0])
            self.assertNotIn("/data/HK/", call.args[0])

    def test_mixed_batch_routes_each_symbol_and_preserves_input_order(self):
        result = Tickers(["0700.hk", "AAPL", "2800.HK"], max_workers=3).price()
        self.assertEqual(result["symbol"].tolist(),
                         ["0700.HK", "0700.HK", "AAPL", "AAPL", "2800.HK", "2800.HK"])
        self.assertEqual(list(result.columns), COLUMNS)

    def test_mcp_price_inherits_hk_routing_and_date_filters(self):
        # Load the standalone tool without starting the optional MCP server.
        package = ModuleType("defeatbeta_mcp")
        package.__path__ = [str(Path(__file__).resolve().parents[1] / "mcp" / "src" / "defeatbeta_mcp")]
        with patch.dict(sys.modules, {"defeatbeta_mcp": package}):
            tool = import_module("defeatbeta_mcp.tools.price")
            result = tool.get_stock_price("0700.hk", "2026-11-09", "2026-11-09")
            self.assertEqual(result["symbol"], "0700.HK")
            self.assertEqual(result["rows_returned"], 1)
            self.assertFalse(result["truncated"])
            self.assertEqual(result["latest_close"], 11.25)
            self.assertEqual(result["data"], [{
                "report_date": "2026-11-09", "open": 10.125, "high": 12.5,
                "low": 9.75, "close": 11.25, "volume": 123456}])
            self.assertIn("No historical data", tool.get_stock_price("1234.HK")["message"])

    def test_concurrent_markets_do_not_change_each_others_routes(self):
        symbols = ["AAPL", "0700.HK", "2800.HK", "9988.HK"] * 4
        with ThreadPoolExecutor(max_workers=4) as executor:
            frames = list(executor.map(lambda symbol: Ticker(symbol).price(), symbols))
        for symbol, frame in zip(symbols, frames):
            self.assertEqual(frame["symbol"].tolist(), [symbol, symbol])


@unittest.skipUnless(os.environ.get("DEFEATBETA_RUN_NETWORK_TESTS") == "1",
                     "Set DEFEATBETA_RUN_NETWORK_TESTS=1 to query published prices")
class TestHKPriceNetwork(unittest.TestCase):
    def test_acceptance_symbols_and_mixed_market_batch(self):
        proxy = os.environ.get("DEFEATBETA_TEST_HTTP_PROXY")
        with TemporaryDirectory() as directory:
            config = Configuration(cache_directory=directory)
            tickers = Tickers(["AAPL", *HK_SYMBOLS], http_proxy=proxy,
                              config=config, log_level=logging.WARNING, max_workers=3)
            try:
                result = tickers.price()
                self.assertEqual(set(result["symbol"]), {"AAPL", *HK_SYMBOLS})
                self.assertEqual(list(result.columns), COLUMNS)
                for symbol in HK_SYMBOLS:
                    frame = result[result["symbol"] == symbol]
                    self.assertGreater(len(frame), 1000)
                    self.assertEqual(frame["symbol"].iloc[0], symbol)
                    self.assertTrue(frame["report_date"].notna().all())
                    self.assertTrue((frame["volume"] >= 0).all())
            finally:
                tickers._ticker_map["AAPL"].duckdb_client.close()


if __name__ == "__main__":
    unittest.main()
