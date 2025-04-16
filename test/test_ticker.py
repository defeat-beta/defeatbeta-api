import logging
import unittest

from data.ticker import Ticker


class TestDuckDBClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ticker = Ticker("BABA", http_proxy="http://127.0.0.1:33210")

    @classmethod
    def tearDownClass(cls):
        cls.ticker.__del__()

    def test_data_time(self):
        result = self.ticker.data_time()
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

    def test_revenue_forecasts(self):
        result = self.ticker.revenue_forecasts()
        print(result.to_string(float_format="{:,}".format))