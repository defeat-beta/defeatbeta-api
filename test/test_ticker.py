import logging
import unittest

from defeatbeta_api import data_update_time
from defeatbeta_api.data.ticker import Ticker

class TestTicker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ticker = Ticker("BABA", http_proxy="http://127.0.0.1:33210", log_level=logging.DEBUG)

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
        print(result.pretty_table())
        print(result.df().to_string())

    def test_statement_2(self):
        result = self.ticker.annual_income_statement()
        print(result.pretty_table())
        print(result.df().to_string())

    def test_statement_3(self):
        result = self.ticker.quarterly_balance_sheet()
        print(result.pretty_table())
        print(result.df().to_string())

    def test_statement_4(self):
        result = self.ticker.annual_balance_sheet()
        print(result.pretty_table())
        print(result.df().to_string())

    def test_statement_5(self):
        result = self.ticker.quarterly_cash_flow()
        print(result.pretty_table())
        print(result.df().to_string())

    def test_statement_6(self):
        result = self.ticker.annual_cash_flow()
        print(result.pretty_table())
        print(result.df().to_string())

    def test_ttm_pe(self):
        result = self.ticker.ttm_pe()
        print(result.to_string())

    def test_quarterly_gross_margin(self):
        result = self.ticker.quarterly_gross_margin()
        print(result.to_string())

    def test_earning_call_transcripts(self):
        transcripts = self.ticker.earning_call_transcripts()
        print(transcripts)
        print(transcripts.get_transcripts_list())
        print(transcripts.get_transcript(2025, 2))
        print(transcripts.pretty_table(2025, 2))
