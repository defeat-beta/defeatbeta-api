"""Verify batched monthly alignment against independent company-level alignment."""

from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from defeatbeta_api.data.ticker import Ticker
from test import test_industry_currency as fixtures


FIRST = '_income'
SECOND = '_assets'


def legacy_alignment(ticker, table, baseline, currencies):
    """Preserve the former paired dropna and two-merge algorithm as a reference."""
    result = baseline.reset_index(drop=True).copy()
    rates = {}
    for column in table.columns:
        if not column.endswith(FIRST):
            continue
        symbol = column[:-len(FIRST)]
        other = symbol + SECOND
        if other not in table:
            continue
        fx = ticker._industry_currency_rates(table['report_date'], currencies.get(symbol, 'USD'), rates)
        pair = pd.DataFrame({
            'report_date': table['report_date'],
            column: (table[column] / fx).values,
            other: (table[other] / fx).values,
        }).dropna()
        for name in (column, other):
            result[name] = pd.merge_asof(baseline, pair[['report_date', name]],
                                         on='report_date', direction='backward')[name]
    return result


class TestIndustryAlignment(unittest.TestCase):
    def baseline(self):
        return pd.DataFrame({'report_date': pd.date_range('2023-12-31', '2024-05-31', freq='ME')
                             .astype('datetime64[us]')})

    def table(self):
        # An incomplete last row must retain the last complete pair for that company.
        return pd.DataFrame({
            'report_date': pd.to_datetime(['2024-01-15', '2024-02-15', '2024-02-15', '2024-04-01'])
                .astype('datetime64[us]'),
            'A_income': [1.0, 3.0, 5.0, np.nan], 'A_assets': [2.0, np.nan, 6.0, 8.0],
            'B_income': [np.nan, 10.0, np.nan, 20.0], 'B_assets': [9.0, 11.0, 12.0, 21.0],
            'C_income': [np.nan] * 4, 'C_assets': [np.nan] * 4,
            'SKIP_income': [1.0] * 4,
        })

    def align(self, ticker, table, baseline=None, currencies=None):
        return ticker._industry_monthly_pairs(table, self.baseline() if baseline is None else baseline,
                                              currencies or {}, FIRST, SECOND)

    def assert_reference(self, table, currencies=None, scenario='normal', baseline=None):
        baseline = self.baseline() if baseline is None else baseline
        expected = legacy_alignment(fixtures.subject(scenario), table, baseline, currencies or {})
        actual = self.align(fixtures.subject(scenario), table, baseline, currencies)
        assert_frame_equal(actual, expected, check_exact=True)
        return actual

    def test_each_public_calculation_uses_one_monthly_merge(self):
        for method in fixtures.PAIRS:
            with self.subTest(method=method):
                ticker = fixtures.subject()
                original = pd.merge_asof
                monthly_calls = []

                def merge(left, right, *args, **kwargs):
                    if 'close' not in right:
                        monthly_calls.append(tuple(right.columns))
                    return original(left, right, *args, **kwargs)

                with patch('defeatbeta_api.data.ticker.load_sql', side_effect=lambda name, **kw: name), \
                     patch('defeatbeta_api.data.ticker.pd.merge_asof', side_effect=merge):
                    getattr(ticker, method)()
                self.assertEqual(len(monthly_calls), 1)

    def test_public_aggregation_keeps_original_company_addition_order(self):
        ticker = fixtures.subject()
        ticker.company_meta.get_financial_currency_map = lambda: {}
        dates = pd.to_datetime(['2024-01-31', '2024-02-29']).astype('datetime64[us]')
        table = pd.DataFrame({'report_date': dates})
        for symbol, income, equity in [('AAA', 1e16, 1e16), ('BBB', 1.0, 2.0),
                                       ('CCC', -1e16, -1e16), ('DDD', 2.0, 4.0)]:
            table[symbol + '_ttm_net_income'] = income
            table[symbol + '_ttm_avg_equity'] = equity
        query = ticker.duckdb_client.query.side_effect
        ticker.duckdb_client.query.side_effect = lambda sql: (
            table.copy(deep=True) if sql == 'select_ttm_roe_by_industry' else query(sql))
        with patch('defeatbeta_api.data.ticker.load_sql', side_effect=lambda name, **kw: name):
            result = ticker.industry_roe()
        self.assertEqual(result['total_ttm_net_income'].tolist(), [2.0, 2.0])
        self.assertEqual(result['total_avg_equity'].tolist(), [6.0, 6.0])
        self.assertEqual(result['industry_roe'].tolist(), [0.3333, 0.3333])

    def test_partial_pairs_and_duplicate_dates_keep_the_last_complete_pair(self):
        actual = self.assert_reference(self.table(), {'SKIP': 'JPY'})
        self.assertEqual(actual.loc[2, 'A_income'], 5.0)
        self.assertEqual(actual.loc[2, 'A_assets'], 6.0)
        self.assertEqual(actual.loc[4, 'A_income'], 5.0)
        self.assertEqual(actual.loc[4, 'A_assets'], 6.0)
        self.assertEqual(actual.loc[2, 'B_income'], 10.0)
        self.assertTrue(actual.loc[0].drop('report_date').isna().all())
        self.assertTrue(actual[['C_income', 'C_assets']].isna().all().all())
        self.assertNotIn('SKIP_income', actual)

    def test_mixed_currencies_and_missing_early_fx_coverage(self):
        table = self.table().rename(columns={'A_income': 'BBB_income', 'A_assets': 'BBB_assets',
                                             'B_income': 'DDD_income', 'B_assets': 'DDD_assets'})
        self.assert_reference(table, {'BBB': 'CNY', 'DDD': 'EUR', 'SKIP': 'JPY'})

    def test_zero_infinite_and_nullable_values_preserve_reference_dtypes(self):
        for dtype in ('float64', 'Float64', 'Float32'):
            for scenario in ('normal', 'extreme'):
                with self.subTest(dtype=dtype, scenario=scenario):
                    table = self.table().rename(columns={'A_income': 'BBB_income', 'A_assets': 'BBB_assets'})
                    table['BBB_income'] = pd.Series([0.0, np.nan, np.inf, -np.inf], dtype=dtype)
                    table['BBB_assets'] = pd.Series([0.0, 1.0, 2.0, np.nan], dtype=dtype)
                    self.assert_reference(table, {'BBB': 'CNY'}, scenario)

    def test_empty_inputs_empty_baseline_and_no_paired_columns(self):
        table = self.table()
        self.assert_reference(table.iloc[:0])
        self.assert_reference(table, baseline=self.baseline().iloc[:0])
        self.assert_reference(table[['report_date', 'SKIP_income']], {'SKIP': 'JPY'})

    def test_random_missing_patterns_match_company_level_alignment_exactly(self):
        rng = np.random.default_rng(73)
        for iteration in range(20):
            with self.subTest(iteration=iteration):
                dates = pd.to_datetime('2024-01-01') + pd.to_timedelta(np.sort(rng.integers(0, 120, 25)), unit='D')
                table = pd.DataFrame({'report_date': dates.astype('datetime64[us]')})
                for symbol in ['AAA', 'BBB', 'CCC', 'DDD']:
                    for suffix in (FIRST, SECOND):
                        values = rng.normal(size=len(table))
                        values[rng.random(len(table)) < 0.4] = np.nan
                        table[symbol + suffix] = values
                self.assert_reference(table, {'BBB': 'CNY', 'CCC': 'CNY', 'DDD': 'EUR'})

    def test_batch_alignment_does_not_mutate_inputs_or_share_results(self):
        table, baseline = self.table(), self.baseline()
        original_table, original_baseline = table.copy(deep=True), baseline.copy(deep=True)
        expected = legacy_alignment(fixtures.subject(), table, baseline, {})
        ticker = fixtures.subject()
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: self.align(ticker, table, baseline), range(4)))
        results[0].loc[2, 'A_income'] = -999.0
        for result in results[1:]:
            assert_frame_equal(result, expected, check_exact=True)
        assert_frame_equal(table, original_table, check_exact=True)
        assert_frame_equal(baseline, original_baseline, check_exact=True)


if __name__ == '__main__':
    unittest.main()
