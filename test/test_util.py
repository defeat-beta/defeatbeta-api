import unittest

from defeatbeta_api.utils.util import load_finance_template, load_sp500_historical_annual_returns, sp500_cagr_returns, \
    sp500_cagr_returns_rolling
from defeatbeta_api.utils.const import income_statement


class TestUtil(unittest.TestCase):

    def test_load_finance_template(self):
        template = load_finance_template(income_statement, "default")
        print(template)
        self.assertIsNotNone(template)
        template = load_finance_template(income_statement, "bank")
        print(template)
        self.assertIsNotNone(template)
        template = load_finance_template(income_statement, "insurance")
        print(template)
        self.assertIsNotNone(template)

    def test_load_sp500_historical_annual_returns(self):
        sp500_returns = load_sp500_historical_annual_returns()
        print(sp500_returns)
        print(sp500_cagr_returns(10))
        print(sp500_cagr_returns_rolling(10).to_string())