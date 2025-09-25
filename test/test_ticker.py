import logging
import unittest

from defeatbeta_api import data_update_time
from defeatbeta_api.data.ticker import Ticker

class TestTicker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ticker = Ticker("TSLA", http_proxy="http://127.0.0.1:33210", log_level=logging.DEBUG)

    @classmethod
    def tearDownClass(cls):
        result = cls.ticker.download_data_performance()
        print(result)

    def test_data_time(self):
        result = data_update_time
        print("data_time=>" + result)

    def test_info(self):
        result = self.ticker.info()
        print(result.to_string())

    def test_officers(self):
        result = self.ticker.officers()
        print(result.to_string())

    def test_calendar(self):
        result = self.ticker.calendar()
        print(result.to_string())

    def test_earnings(self):
        result = self.ticker.earnings()
        print(result.to_string())

    def test_splits(self):
        result = self.ticker.splits()
        print(result.to_string())

    def test_dividends(self):
        result = self.ticker.dividends()
        print(result.to_string())

    def test_revenue_forecast(self):
        result = self.ticker.revenue_forecast()
        print(result.to_string(float_format="{:,}".format))

    def test_earnings_forecast(self):
        result = self.ticker.earnings_forecast()
        print(result.to_string(float_format="{:,}".format))

    def test_summary(self):
        result = self.ticker.summary()
        print(result.to_string(float_format="{:,}".format))

    def test_ttm_eps(self):
        result = self.ticker.ttm_eps()
        print(result.to_string(float_format="{:,}".format))

    def test_price(self):
        result = self.ticker.price()
        print(result)

    def test_statement_1(self):
        result = self.ticker.quarterly_income_statement()
        result.print_pretty_table()
        print(result.df().to_string())

    def test_statement_2(self):
        result = self.ticker.annual_income_statement()
        result.print_pretty_table()
        print(result.df().to_string())

    def test_statement_3(self):
        result = self.ticker.quarterly_balance_sheet()
        result.print_pretty_table()
        print(result.df().to_string())

    def test_statement_4(self):
        result = self.ticker.annual_balance_sheet()
        result.print_pretty_table()
        print(result.df().to_string())

    def test_statement_5(self):
        result = self.ticker.quarterly_cash_flow()
        result.print_pretty_table()
        print(result.df().to_string())

    def test_statement_6(self):
        result = self.ticker.annual_cash_flow()
        result.print_pretty_table()
        print(result.df().to_string())

    def test_ttm_pe(self):
        result = self.ticker.ttm_pe()
        print(result)

    def test_earning_call_transcripts(self):
        transcripts = self.ticker.earning_call_transcripts()
        print(transcripts)
        print(transcripts.get_transcripts_list())
        print(transcripts.get_transcript(2025, 2))
        transcripts.print_pretty_table(2025, 2)

    def test_news(self):
        news = self.ticker.news()
        print(news)
        print(news.get_news_list())
        print(news.get_news("b67526eb-581a-35b2-8357-b4f282fe876f"))
        news.print_pretty_table("b67526eb-581a-35b2-8357-b4f282fe876f")

    def test_revenue_by_segment(self):
        result = self.ticker.revenue_by_segment()
        print(result.to_string())

    def test_revenue_by_geography(self):
        result = self.ticker.revenue_by_geography()
        print(result.to_string())

    def test_revenue_by_product(self):
        result = self.ticker.revenue_by_product()
        print(result.to_string())

    def test_quarterly_gross_margin(self):
        result = self.ticker.quarterly_gross_margin()
        print(result.to_string())

    def test_annual_gross_margin(self):
        result = self.ticker.annual_gross_margin()
        print(result.to_string())

    def test_quarterly_operating_margin(self):
        result = self.ticker.quarterly_operating_margin()
        print(result.to_string())

    def test_annual_operating_margin(self):
        result = self.ticker.annual_operating_margin()
        print(result.to_string())

    def test_quarterly_net_margin(self):
        result = self.ticker.quarterly_net_margin()
        print(result.to_string())

    def test_annual_net_margin(self):
        result = self.ticker.annual_net_margin()
        print(result.to_string())

    def test_quarterly_ebitda_margin(self):
        result = self.ticker.quarterly_ebitda_margin()
        print(result.to_string())

    def test_annual_ebitda_margin(self):
        result = self.ticker.annual_ebitda_margin()
        print(result.to_string())

    def test_quarterly_fcf_margin(self):
        result = self.ticker.quarterly_fcf_margin()
        print(result.to_string())

    def test_annual_fcf_margin(self):
        result = self.ticker.annual_fcf_margin()
        print(result.to_string())

    def test_quarterly_revenue_yoy_growth(self):
        result = self.ticker.quarterly_revenue_yoy_growth()
        print(result.to_string())

    def test_annual_revenue_yoy_growth(self):
        result = self.ticker.annual_revenue_yoy_growth()
        print(result.to_string())

    def test_quarterly_operating_income_yoy_growth(self):
        result = self.ticker.quarterly_operating_income_yoy_growth()
        print(result.to_string())

    def test_annual_operating_income_yoy_growth(self):
        result = self.ticker.annual_operating_income_yoy_growth()
        print(result.to_string())

    def test_quarterly_net_income_yoy_growth(self):
        result = self.ticker.quarterly_net_income_yoy_growth()
        print(result.to_string())

    def test_annual_net_income_yoy_growth(self):
        result = self.ticker.annual_net_income_yoy_growth()
        print(result.to_string())

    def test_quarterly_fcf_yoy_growth(self):
        result = self.ticker.quarterly_fcf_yoy_growth()
        print(result.to_string())

    def test_annual_fcf_yoy_growth(self):
        result = self.ticker.annual_fcf_yoy_growth()
        print(result.to_string())

    def test_quarterly_eps_yoy_growth(self):
        result = self.ticker.quarterly_eps_yoy_growth()
        print(result.to_string())

    def test_quarterly_ttm_eps_yoy_growth(self):
        result = self.ticker.quarterly_ttm_eps_yoy_growth()
        print(result.to_string())

    def test_market_capitalization(self):
        result = self.ticker.market_capitalization()
        print(result.to_string())

    def test_ps_ratio(self):
        result = self.ticker.ps_ratio()
        print(result.to_string())

    def test_pb_ratio(self):
        result = self.ticker.pb_ratio()
        print(result.to_string())

    def test_peg_ratio(self):
        result = self.ticker.peg_ratio()
        print(result.to_string())

    def test_ttm_revenue(self):
        result = self.ticker.ttm_revenue()
        print(result.to_string())

    def test_ttm_net_income_common_stockholders(self):
        result = self.ticker.ttm_net_income_common_stockholders()
        print(result.to_string())

    def test_quarterly_book_value_of_equity(self):
        result = self.ticker._quarterly_book_value_of_equity()
        print(result.to_string())

    def test_roe(self):
        result = self.ticker.roe()
        print(result.to_string())

    def test_roa(self):
        result = self.ticker.roa()
        print(result.to_string())

    def test_roic(self):
        result = self.ticker.roic()
        print(result.to_string())

    def test_equity_multiplier(self):
        result = self.ticker.equity_multiplier()
        print(result.to_string())

    def test_asset_turnover(self):
        result = self.ticker.asset_turnover()
        print(result.to_string())
