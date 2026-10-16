"""Check industry capitalization against independently specified historical values."""

from datetime import date
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import duckdb
import pandas as pd

from defeatbeta_api.data.sql.sql_loader import load_sql
from defeatbeta_api.data.ticker import Ticker


class TestIndustryMarketCap(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.connection = duckdb.connect(config={"threads": 1})
        self.addCleanup(self.connection.close)

    def write_table(self, name, schema, rows, reverse=False):
        self.connection.execute(f"CREATE OR REPLACE TABLE {name} ({schema})")
        if rows:
            placeholders = ", ".join("?" for _ in rows[0])
            self.connection.executemany(f"INSERT INTO {name} VALUES ({placeholders})", rows)
        path = self.root / f"{name}.parquet"
        order = "DESC" if reverse else "ASC"
        self.connection.execute(
            f"COPY (SELECT * FROM {name} ORDER BY ALL {order}) TO ? (FORMAT PARQUET)", [str(path)])
        return str(path)

    def query(self, prices, shares, symbols=("TEST",), threads=1, reverse=False):
        price_path = self.write_table(
            "stock_prices", "symbol VARCHAR, report_date DATE, close DOUBLE", prices, reverse)
        share_path = self.write_table(
            "stock_shares_outstanding", "symbol VARCHAR, report_date DATE, shares_outstanding BIGINT",
            shares, reverse)
        self.connection.execute(f"SET threads = {threads}")
        sql = load_sql("select_market_cap_by_industry", stock_prices=price_path,
                       stock_shares_outstanding=share_path,
                       symbols=", ".join(f"'{symbol}'" for symbol in symbols))
        return self.connection.sql(sql).fetchall()

    def test_latest_share_selection_is_independent_of_order_and_threads(self):
        prices = [("TEST", "2026-01-03", 10)]
        shares = [("TEST", "2026-01-01", 100), ("TEST", "2026-01-02", 200),
                  ("TEST", "2026-01-04", 300)]
        for threads in (1, 4):
            for reverse in (False, True):
                with self.subTest(threads=threads, reverse=reverse):
                    self.assertEqual(self.query(prices, shares, threads=threads, reverse=reverse),
                                     [(date(2026, 1, 3), 2000.0)])

    def test_each_price_selects_its_own_latest_share_including_same_day(self):
        prices = [("TEST", "2026-01-01", 10), ("TEST", "2026-01-03", 10),
                  ("TEST", "2026-01-04", 10), ("TEST", "2026-01-05", 10)]
        shares = [("TEST", "2026-01-01", 100), ("TEST", "2026-01-02", 200),
                  ("TEST", "2026-01-04", 300)]
        self.assertEqual(self.query(prices, shares), [
            (date(2026, 1, 1), 1000.0), (date(2026, 1, 3), 2000.0),
            (date(2026, 1, 4), 3000.0), (date(2026, 1, 5), 3000.0)])

    def test_symbols_are_isolated_and_unrequested_prices_are_excluded(self):
        prices = [("AAA", "2026-01-03", 10), ("BBB", "2026-01-02", 20),
                  ("UNREQUESTED", "2026-01-01", 1000)]
        shares = [("AAA", "2026-01-01", 100), ("AAA", "2026-01-02", 200),
                  ("BBB", "2026-01-01", 7), ("BBB", "2026-01-03", 70)]
        self.assertEqual(self.query(prices, shares, symbols=("AAA", "BBB")), [
            (date(2026, 1, 2), None, 140.0), (date(2026, 1, 3), 2000.0, None)])

    def test_missing_history_retains_prices_without_using_future_or_other_symbols(self):
        prices = [("TEST", "2025-12-31", 10), ("MISSING", "2026-01-03", 20)]
        shares = [("TEST", "2026-01-01", 100)]
        self.assertEqual(self.query(prices, shares, symbols=("TEST", "MISSING")), [
            (date(2025, 12, 31), None, None), (date(2026, 1, 3), None, None)])
        self.assertEqual(self.query(prices, [], symbols=("TEST", "MISSING")), [
            (date(2025, 12, 31), None, None), (date(2026, 1, 3), None, None)])

    def test_public_industry_valuations_use_the_latest_share_counts(self):
        self.write_table("stock_profile", "symbol VARCHAR, industry VARCHAR",
                         [("AAA", "Test Industry"), ("BBB", "Test Industry")])
        self.write_table("stock_prices", "symbol VARCHAR, report_date VARCHAR, close DOUBLE", [
            ("AAA", "2026-01-02", 10), ("AAA", "2026-01-05", 10),
            ("BBB", "2026-01-02", 20), ("BBB", "2026-01-05", 20)])
        self.write_table("stock_shares_outstanding",
                         "symbol VARCHAR, report_date VARCHAR, shares_outstanding BIGINT", [
            ("AAA", "2026-01-01", 100), ("AAA", "2026-01-03", 200),
            ("BBB", "2026-01-01", 10), ("BBB", "2026-01-04", 20)])
        statements = [
            (symbol, report_date, item, "quarterly", value)
            for symbol, revenue, income, equity in (("AAA", 100, 10, 500), ("BBB", 200, 20, 1000))
            for report_date in ("2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31")
            for item, value in (("total_revenue", revenue), ("net_income_common_stockholders", income),
                                ("stockholders_equity", equity))
        ]
        self.write_table("stock_statement", "symbol VARCHAR, report_date VARCHAR, item_name VARCHAR, "
                         "period_type VARCHAR, item_value DOUBLE", statements)
        ticker = Ticker.__new__(Ticker)
        ticker.ticker = "AAA"
        ticker.info = lambda: pd.DataFrame({"industry": ["Test Industry"]})
        ticker.huggingface_client = SimpleNamespace(
            get_url_path=lambda name: str(self.root / f"{name}.parquet"))
        ticker.duckdb_client = SimpleNamespace(query=lambda sql: self.connection.sql(sql).df())
        ticker.company_meta = SimpleNamespace(get_financial_currency_map=lambda: {"AAA": "USD", "BBB": "USD"})
        for method, ratio, expected in (
                ("industry_pb_ratio", "industry_pb_ratio", [0.8, 1.6]),
                ("industry_ps_ratio", "industry_ps_ratio", [1.0, 2.0]),
                ("industry_ttm_pe", "industry_pe", [10.0, 20.0])):
            with self.subTest(method=method):
                result = getattr(ticker, method)()
                self.assertEqual(result["report_date"].dt.strftime("%Y-%m-%d").tolist(),
                                 ["2026-01-02", "2026-01-05"])
                self.assertEqual(result["total_market_cap"].tolist(), [1200.0, 2400.0])
                self.assertEqual(result[ratio].tolist(), expected)


if __name__ == "__main__":
    unittest.main()
