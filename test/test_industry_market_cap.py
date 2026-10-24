"""Exercise historical-share selection and complete valuation calculations offline."""

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import duckdb
import pandas as pd
from pandas.testing import assert_frame_equal

from defeatbeta_api.data.sql.sql_loader import load_sql
from defeatbeta_api.data.ticker import Ticker


class TestIndustryMarketCap(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.connection = duckdb.connect(config={'threads': 4})
        self.addCleanup(self.connection.close)

    def parquet(self, name, schema, rows):
        self.connection.execute(f'CREATE TABLE {name} ({schema})')
        if rows:
            placeholders = ','.join('?' for _ in rows[0])
            self.connection.executemany(f'INSERT INTO {name} VALUES ({placeholders})', rows)
        path = self.directory / (name + '.parquet')
        self.connection.execute(f"COPY {name} TO '{path.as_posix()}' (FORMAT PARQUET)")
        return path.as_posix()

    def fixture(self, prices, shares):
        self.prices = self.parquet('stock_prices',
            'symbol VARCHAR, report_date VARCHAR, close DECIMAL(16,4)', prices)
        self.shares = self.parquet('stock_shares_outstanding',
            'symbol VARCHAR, report_date VARCHAR, shares_outstanding BIGINT', shares)

    def market(self, symbols=('A',)):
        sql = load_sql('select_market_cap_by_industry', stock_prices=self.prices,
            stock_shares_outstanding=self.shares,
            symbols=', '.join("'" + symbol + "'" for symbol in symbols))
        return self.connection.execute(sql).fetchdf()

    def test_latest_null_does_not_fall_back_to_an_older_value(self):
        self.fixture([('A', '2024-03-01', 10)],
                     [('A', '2024-01-01', 100), ('A', '2024-02-01', None)])
        self.assertTrue(pd.isna(self.market().iloc[0]['A']))

    def test_nearest_prior_and_same_day_shares_without_future_leakage(self):
        self.fixture([('A', '2024-01-15', 10), ('A', '2024-02-01', 10),
                      ('A', '2024-02-15', 10)],
                     [('A', '2024-03-01', 300), ('A', '2024-01-01', 100),
                      ('A', '2024-02-01', 200)])
        self.assertEqual(self.market()['A'].tolist(), [1000, 2000, 2000])

    def test_pre_history_and_unmatched_symbols_remain_null(self):
        self.fixture([('A', '2023-12-01', 10), ('B', '2024-02-01', 10)],
                     [('A', '2024-01-01', 100)])
        result = self.market(('A', 'B'))
        self.assertEqual(result['report_date'].tolist(), ['2023-12-01', '2024-02-01'])
        self.assertTrue(result[['A', 'B']].isna().all().all())

    def test_zero_shares_and_null_price_are_preserved(self):
        self.fixture([('A', '2024-02-01', 10), ('A', '2024-02-02', None)],
                     [('A', '2024-01-01', 0)])
        result = self.market()
        self.assertEqual(result.iloc[0]['A'], 0)
        self.assertTrue(pd.isna(result.iloc[1]['A']))

    def test_empty_prices_preserve_output_schema(self):
        self.fixture([], [('A', '2024-01-01', 100)])
        result = self.market()
        self.assertTrue(result.empty)
        self.assertEqual(list(result), ['report_date', 'A'])

    def test_empty_shares_preserve_price_dates(self):
        self.fixture([('A', '2024-02-01', 10)], [])
        result = self.market()
        self.assertEqual(len(result), 1)
        self.assertTrue(pd.isna(result.iloc[0]['A']))

    def test_identical_duplicate_records_do_not_change_values(self):
        self.fixture([('A', '2024-02-01', 10), ('A', '2024-02-01', 10)],
                     [('A', '2024-01-01', 100), ('A', '2024-01-01', 100)])
        result = self.market()
        self.assertEqual(result['A'].tolist(), [1000])

    def test_decimal_rounding_is_preserved(self):
        self.fixture([('A', '2024-02-01', '1.0050'), ('A', '2024-02-02', '-1.0050')],
                     [('A', '2024-01-01', 1)])
        self.assertEqual(self.market()['A'].tolist(), [1.01, -1.01])

    def valuation_subject(self):
        self.fixture([(s, d, 10) for s in ('A', 'B', 'C', 'D')
                      for d in ('2023-12-31', '2024-01-31')],
                     [('A', '2023-01-01', 10), ('A', '2023-12-31', 20),
                      ('A', '2024-01-31', 30), ('A', '2025-01-01', 999),
                      ('B', '2023-01-01', 30), ('C', '2023-01-01', 40),
                      ('D', '2023-01-01', 50), ('D', '2023-12-31', None)])
        self.parquet('stock_profile', 'symbol VARCHAR, industry VARCHAR',
                     [(s, 'Example') for s in ('A', 'B', 'C', 'D')])
        statements = []
        for symbol, income, revenue, equity in [('A', 10, 20, 100), ('B', -5, 10, -50), ('D', 5, 5, 50)]:
            for date in ('2023-03-31', '2023-06-30', '2023-09-30', '2023-12-31'):
                for item, value in [('net_income_common_stockholders', income),
                                    ('total_revenue', revenue), ('stockholders_equity', equity)]:
                    statements.append((symbol, date, item, value, 'quarterly'))
        self.parquet('stock_statement', 'symbol VARCHAR, report_date VARCHAR, item_name VARCHAR, '
                     'item_value DECIMAL(18,4), period_type VARCHAR', statements)
        self.parquet('exchange_rate', 'symbol VARCHAR, report_date VARCHAR, close DECIMAL(16,4)',
                     [('CNY=X', '2023-01-01', 2)])
        ticker = Ticker.__new__(Ticker)
        ticker.ticker = 'A'
        ticker.huggingface_client = SimpleNamespace(
            get_url_path=lambda name: (self.directory / (name + '.parquet')).as_posix())
        ticker.duckdb_client = SimpleNamespace(query=lambda sql: self.connection.execute(sql).fetchdf())
        ticker.company_meta = SimpleNamespace(
            get_financial_currency_map=lambda: {'A': 'USD', 'B': 'CNY', 'C': 'USD', 'D': 'USD'})
        return ticker

    def test_complete_pe_ps_pb_results_with_paired_exclusions_and_currency(self):
        ticker = self.valuation_subject()
        for method, denominator, numerator, values, ratio, ratios in [
            ('industry_ttm_pe', 'total_ttm_net_income', [200.0, 300.0], [40.0, 40.0], 'industry_pe', [5.0, 7.5]),
            ('industry_ps_ratio', 'total_ttm_revenue', [500.0, 600.0], [100.0, 100.0], 'industry_ps_ratio', [5.0, 6.0]),
            ('industry_pb_ratio', 'total_bve', [200.0, 300.0], [100.0, 100.0], 'industry_pb_ratio', [2.0, 3.0]),
        ]:
            with self.subTest(method=method):
                expected = pd.DataFrame({
                    'report_date': pd.to_datetime(['2023-12-31', '2024-01-31']).astype('datetime64[us]'),
                    'industry': ['Example', 'Example'], 'total_market_cap': numerator,
                    denominator: values, ratio: ratios})
                for _ in range(2):
                    assert_frame_equal(getattr(ticker, method)(), expected, check_exact=True)

    def test_new_call_observes_changed_shares(self):
        ticker = self.valuation_subject()
        before = ticker.industry_pb_ratio()
        self.connection.execute("UPDATE stock_shares_outstanding SET shares_outstanding=60 "
                                "WHERE symbol='A' AND report_date='2024-01-31'")
        path = self.directory / 'updated_shares.parquet'
        self.connection.execute(f"COPY stock_shares_outstanding TO '{path.as_posix()}' (FORMAT PARQUET)")
        original = ticker.huggingface_client.get_url_path
        ticker.huggingface_client.get_url_path = lambda name: (
            path.as_posix() if name == 'stock_shares_outstanding' else original(name))
        after = ticker.industry_pb_ratio()
        self.assertEqual(before['industry_pb_ratio'].tolist(), [2.0, 3.0])
        self.assertEqual(after['industry_pb_ratio'].tolist(), [2.0, 6.0])


if __name__ == '__main__':
    unittest.main()
