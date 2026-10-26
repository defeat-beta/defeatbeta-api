"""Reject DCF for tickers whose WACC exists but whose annual statements do not."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import pandas as pd

from defeatbeta_api.data.ticker import Ticker


WACC = {
    "report_date": "2026-09-30",
    "treasure_10y_yield": 0.04,
    "market_capitalization": 1.0e9,
    "total_debt_usd": 1.0e8,
    "interest_expense_usd": 5.0e6,
    "beta_5y": 1.1,
    "sp500_10y_cagr": 0.1,
    "tax_rate_for_calcs": 0.21,
    "pretax_income_usd": 1.0e7,
    "tax_provision_usd": 2.1e6,
}


def subject():
    """Return a ticker with a WACC row and no annual statement data."""
    ticker = Ticker.__new__(Ticker)
    ticker.ticker = "AAA"
    ticker.wacc = Mock(return_value=pd.DataFrame([WACC]))
    ticker.annual_revenue_yoy_growth = Mock(return_value=pd.DataFrame(
        columns=["symbol", "report_date", "revenue", "prev_year_revenue", "yoy_growth"]))
    empty = Mock(return_value=pd.DataFrame())
    for name in ["quarterly_ttm_eps_yoy_growth", "ttm_fcf", "ttm_revenue",
                 "market_capitalization", "price", "annual_fcf_margin"]:
        setattr(ticker, name, empty)
    ticker.quarterly_balance_sheet = Mock(return_value=SimpleNamespace(df=lambda: pd.DataFrame()))
    ticker.treasure = SimpleNamespace(daily_treasure_yield=lambda: pd.DataFrame())
    ticker.company_meta = SimpleNamespace(get_company_info=lambda symbol: {"financial_currency": "USD"})
    return ticker


class TestDcfDataWithoutStatements(unittest.TestCase):
    def test_missing_annual_revenue(self):
        with self.assertRaisesRegex(
                ValueError, "Cannot calculate DCF for AAA: annual revenue data is unavailable"):
            subject().dcf_data()


if __name__ == "__main__":
    unittest.main()
