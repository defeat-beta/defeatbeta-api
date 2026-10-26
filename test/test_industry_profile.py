"""Handle industry methods for tickers without a profile or industry data."""

import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

from defeatbeta_api.data.ticker import Ticker
from test.test_industry_currency import PAIRS, subject as populated


METHODS = [
    "industry_ttm_pe",
    "industry_ps_ratio",
    "industry_pb_ratio",
    "industry_roe",
    "industry_roa",
    "industry_roic",
    "industry_equity_multiplier",
    "industry_asset_turnover",
    "industry_quarterly_gross_margin",
    "industry_quarterly_ebitda_margin",
    "industry_quarterly_net_margin",
]


def subject(profile):
    """Return a ticker whose profile is fixed and whose queries must not run."""
    ticker = Ticker.__new__(Ticker)
    ticker.ticker = "AAA"
    ticker.info = Mock(return_value=profile)
    ticker.huggingface_client = Mock(side_effect=AssertionError("no query expected"))
    ticker.duckdb_client = Mock(side_effect=AssertionError("no query expected"))
    return ticker


class TestIndustryProfile(unittest.TestCase):
    def assert_unknown(self, profile):
        for method in METHODS:
            with self.subTest(method=method):
                ticker = subject(profile)
                with self.assertRaisesRegex(ValueError, "Unknown industry for this ticker: AAA"):
                    getattr(ticker, method)()
                ticker.duckdb_client.query.assert_not_called()

    def test_missing_profile_row(self):
        self.assert_unknown(pd.DataFrame(columns=["symbol", "industry"]))

    def test_null_industry(self):
        self.assert_unknown(pd.DataFrame({"symbol": ["AAA"], "industry": [None]}))

    def test_nan_industry(self):
        self.assert_unknown(pd.DataFrame({"symbol": ["AAA"], "industry": [np.nan]}))

    def test_empty_industry(self):
        self.assert_unknown(pd.DataFrame({"symbol": ["AAA"], "industry": [""]}))


class TestIndustryWithoutData(unittest.TestCase):
    """An industry without any row for a metric, e.g. gross margin for banks."""

    PAIRED = [*PAIRS, "industry_equity_multiplier", "industry_asset_turnover"]

    def setUp(self):
        sql = patch("defeatbeta_api.data.ticker.load_sql", side_effect=lambda name, **kw: name)
        sql.start()
        self.addCleanup(sql.stop)

    def empty(self, scenario="normal"):
        ticker = populated(scenario)
        query = ticker.duckdb_client.query.side_effect
        empty_sql = {name for name, _, _ in PAIRS.values()}
        ticker.duckdb_client.query.side_effect = (
            lambda sql: query(sql).iloc[0:0] if sql in empty_sql else query(sql))
        return ticker

    def test_returns_empty_frame_with_the_usual_columns(self):
        for method in self.PAIRED:
            with self.subTest(method=method):
                expected = getattr(populated(), method)()
                result = getattr(self.empty(), method)()
                self.assertTrue(len(expected) > 0)
                self.assertEqual(len(result), 0)
                self.assertEqual(list(result.columns), list(expected.columns))
                self.assertEqual(result["report_date"].dtype, expected["report_date"].dtype)

    def test_unordered_index(self):
        for method in self.PAIRED:
            with self.subTest(method=method):
                self.assertEqual(len(getattr(self.empty("index"), method)()), 0)


if __name__ == "__main__":
    unittest.main()
