import logging
import unittest

import pandas as pd

from defeatbeta_api.data.news import News
from defeatbeta_api.data.statement import Statement
from defeatbeta_api.data.tickers import Tickers
from defeatbeta_api.data.transcripts import Transcripts

SYMBOLS = ["NVDA", "SHOP"]


class TestTickers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tickers = Tickers(SYMBOLS, http_proxy="http://127.0.0.1:8118", log_level=logging.DEBUG)

    # ------------------------------------------------------------------
    # Category 5 – Info
    # ------------------------------------------------------------------

    def test_info(self):
        result = self.tickers.info()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        symbols_in_result = result["symbol"].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_officers(self):
        result = self.tickers.officers()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        symbols_in_result = result["symbol"].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_sec_filing(self):
        result = self.tickers.sec_filing()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        symbols_in_result = result["symbol"].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_news(self):
        result = self.tickers.news()
        self.assertIsInstance(result, dict)
        for s in SYMBOLS:
            self.assertIn(s, result)

        for symbol, news in result.items():
            print(f"\n--- {symbol} ---")
            self.assertIsInstance(news, News)

            df = news.get_news_list()
            print(df.head(2).to_string())
            print('...')
            print(df.tail(2).to_string())


    def test_earning_call_transcripts(self):
        result = self.tickers.earning_call_transcripts()
        self.assertIsInstance(result, dict)
        for s in SYMBOLS:
            self.assertIn(s, result)

        print(result)

    # ------------------------------------------------------------------
    # Category 1 – Finance
    # ------------------------------------------------------------------

    def test_price(self):
        result = self.tickers.price()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        symbols_in_result = result["symbol"].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_splits(self):
        result = self.tickers.splits()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)

    def test_dividends(self):
        result = self.tickers.dividends()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)

    def test_calendar(self):
        result = self.tickers.calendar()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)

    def test_shares(self):
        result = self.tickers.shares()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        symbols_in_result = result["symbol"].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_beta(self):
        result = self.tickers.beta()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        symbols_in_result = result["symbol"].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_beta_custom_period(self):
        result = self.tickers.beta(period="1y", benchmark="QQQ")
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)

    def test_quarterly_income_statement(self):
        result = self.tickers.quarterly_income_statement()
        self.assertIsInstance(result, dict)
        for s in SYMBOLS:
            self.assertIn(s, result)
            self.assertIsInstance(result[s], Statement)
            print(f"\n--- {s} ---")
            result[s].print_pretty_table()
            print(result[s].df().to_string())

    def test_annual_income_statement(self):
        result = self.tickers.annual_income_statement()
        self.assertIsInstance(result, dict)
        for s in SYMBOLS:
            self.assertIn(s, result)
            self.assertIsInstance(result[s], Statement)
            print(f"\n--- {s} ---")
            result[s].print_pretty_table()

    def test_quarterly_balance_sheet(self):
        result = self.tickers.quarterly_balance_sheet()
        self.assertIsInstance(result, dict)
        for s in SYMBOLS:
            self.assertIn(s, result)
            self.assertIsInstance(result[s], Statement)
            print(f"\n--- {s} ---")
            result[s].print_pretty_table()

    def test_annual_balance_sheet(self):
        result = self.tickers.annual_balance_sheet()
        self.assertIsInstance(result, dict)
        for s in SYMBOLS:
            self.assertIn(s, result)
            self.assertIsInstance(result[s], Statement)
            print(f"\n--- {s} ---")
            result[s].print_pretty_table()

    def test_quarterly_cash_flow(self):
        result = self.tickers.quarterly_cash_flow()
        self.assertIsInstance(result, dict)
        for s in SYMBOLS:
            self.assertIn(s, result)
            self.assertIsInstance(result[s], Statement)
            print(f"\n--- {s} ---")
            result[s].print_pretty_table()

    def test_annual_cash_flow(self):
        result = self.tickers.annual_cash_flow()
        self.assertIsInstance(result, dict)
        for s in SYMBOLS:
            self.assertIn(s, result)
            self.assertIsInstance(result[s], Statement)
            print(f"\n--- {s} ---")
            result[s].print_pretty_table()

    def test_ttm_eps(self):
        result = self.tickers.ttm_eps()
        print(result.to_string(float_format="{:,}".format))
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        symbols_in_result = result["symbol"].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_ttm_revenue(self):
        result = self.tickers.ttm_revenue()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)

    def test_ttm_fcf(self):
        result = self.tickers.ttm_fcf()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)

    def test_ttm_net_income_common_stockholders(self):
        result = self.tickers.ttm_net_income_common_stockholders()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)

    def test_revenue_by_segment(self):
        result = self.tickers.revenue_by_segment()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)

    def test_revenue_by_geography(self):
        result = self.tickers.revenue_by_geography()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)

    def test_revenue_by_product(self):
        result = self.tickers.revenue_by_product()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)

    # ------------------------------------------------------------------
    # Category 2 – Value
    # ------------------------------------------------------------------

    def test_ttm_pe(self):
        result = self.tickers.ttm_pe()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_market_capitalization(self):
        result = self.tickers.market_capitalization()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_ps_ratio(self):
        result = self.tickers.ps_ratio()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_pb_ratio(self):
        result = self.tickers.pb_ratio()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_peg_ratio(self):
        result = self.tickers.peg_ratio()
        print(result)
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_roe(self):
        result = self.tickers.roe()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_roa(self):
        result = self.tickers.roa()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_roic(self):
        result = self.tickers.roic()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_equity_multiplier(self):
        result = self.tickers.equity_multiplier()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_asset_turnover(self):
        result = self.tickers.asset_turnover()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_wacc(self):
        result = self.tickers.wacc()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    # ------------------------------------------------------------------
    # Category 3 – Growth
    # ------------------------------------------------------------------

    def test_quarterly_revenue_yoy_growth(self):
        result = self.tickers.quarterly_revenue_yoy_growth()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_annual_revenue_yoy_growth(self):
        result = self.tickers.annual_revenue_yoy_growth()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_quarterly_operating_income_yoy_growth(self):
        result = self.tickers.quarterly_operating_income_yoy_growth()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_annual_operating_income_yoy_growth(self):
        result = self.tickers.annual_operating_income_yoy_growth()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_quarterly_ebitda_yoy_growth(self):
        result = self.tickers.quarterly_ebitda_yoy_growth()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_annual_ebitda_yoy_growth(self):
        result = self.tickers.annual_ebitda_yoy_growth()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_quarterly_net_income_yoy_growth(self):
        result = self.tickers.quarterly_net_income_yoy_growth()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_annual_net_income_yoy_growth(self):
        result = self.tickers.annual_net_income_yoy_growth()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_quarterly_fcf_yoy_growth(self):
        result = self.tickers.quarterly_fcf_yoy_growth()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_annual_fcf_yoy_growth(self):
        result = self.tickers.annual_fcf_yoy_growth()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_quarterly_eps_yoy_growth(self):
        result = self.tickers.quarterly_eps_yoy_growth()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_quarterly_ttm_eps_yoy_growth(self):
        result = self.tickers.quarterly_ttm_eps_yoy_growth()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    # ------------------------------------------------------------------
    # Category 4 – Profitability
    # ------------------------------------------------------------------

    def test_quarterly_gross_margin(self):
        result = self.tickers.quarterly_gross_margin()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_annual_gross_margin(self):
        result = self.tickers.annual_gross_margin()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_quarterly_operating_margin(self):
        result = self.tickers.quarterly_operating_margin()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_annual_operating_margin(self):
        result = self.tickers.annual_operating_margin()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_quarterly_net_margin(self):
        result = self.tickers.quarterly_net_margin()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_annual_net_margin(self):
        result = self.tickers.annual_net_margin()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_quarterly_ebitda_margin(self):
        result = self.tickers.quarterly_ebitda_margin()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_annual_ebitda_margin(self):
        result = self.tickers.annual_ebitda_margin()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_quarterly_fcf_margin(self):
        result = self.tickers.quarterly_fcf_margin()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)

    def test_annual_fcf_margin(self):
        result = self.tickers.annual_fcf_margin()
        print(result.to_string())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertIn('symbol', result.columns)
        symbols_in_result = result['symbol'].str.upper().tolist()
        for s in SYMBOLS:
            self.assertIn(s, symbols_in_result)