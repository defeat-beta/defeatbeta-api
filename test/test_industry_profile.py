"""Reject industry methods for tickers without a usable profile industry."""

import unittest
from unittest.mock import Mock

import numpy as np
import pandas as pd

from defeatbeta_api.data.ticker import Ticker


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


if __name__ == "__main__":
    unittest.main()
