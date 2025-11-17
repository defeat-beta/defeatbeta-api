import logging
import unittest

from defeatbeta_api.data.ticker import Ticker

class TestTicker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
            cls.ticker = Ticker("BABA", http_proxy="http://127.0.0.1:33210", log_level=logging.DEBUG)

    @classmethod
    def tearDownClass(cls):
        result = cls.ticker.download_data_performance()
        print(result)

    def test_industry_ttm_pe(self):
        result = self.ticker.industry_ttm_pe()
        print(result.to_string())

    def test_industry_ps_ratio(self):
        result = self.ticker.industry_ps_ratio()
        print(result)

    def test_ttm_net_income_common_stockholders(self):
        result = self.ticker.ttm_net_income_common_stockholders()
        print(result)
