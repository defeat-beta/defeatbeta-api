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

    def test_calendar(self):
        result = self.ticker.calendar()
        print(result.to_string())

    def test_earnings(self):
        result = self.ticker.earnings()
        print(result.to_string())