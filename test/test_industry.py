import logging
import unittest

from defeatbeta_api.data.ticker import Ticker

class TestTicker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
            cls.ticker = Ticker("TSLA", http_proxy="http://127.0.0.1:33210", log_level=logging.DEBUG)

    @classmethod
    def tearDownClass(cls):
        result = cls.ticker.download_data_performance()
        print(result)

    def test_industry_ttm_pe(self):
        result = self.ticker.ttm_pe()
        print(result)
        result = self.ticker.industry_ttm_pe()
        print(result)

    def test_industry_ps_ratio(self):
        result = self.ticker.ps_ratio()
        print(result)
        result = self.ticker.industry_ps_ratio()
        print(result)

    def test_industry_pb_ratio(self):
        result = self.ticker.pb_ratio()
        print(result)
        result = self.ticker.industry_pb_ratio()
        print(result)

    def test_industry_roe(self):
        result = self.ticker.roe()
        print(result.to_string())
        result = self.ticker.industry_roe()
        print(result.to_string())

    def test_industry_roa(self):
        result = self.ticker.roa()
        print(result.to_string())
        result = self.ticker.industry_roa()
        print(result.to_string())

    def test_industry_em(self):
        result = self.ticker.equity_multiplier()
        print(result.to_string())
        result = self.ticker.industry_equity_multiplier()
        print(result.to_string())

    def test_industry_quarterly_net_margin(self):
        result = self.ticker.quarterly_net_margin()
        print(result.to_string())
        result = self.ticker.industry_quarterly_net_margin()
        print(result.to_string())

    def test_industry_asset_turnover(self):
        result = self.ticker.quarterly_net_margin()
        print(result.to_string())
        result = self.ticker.industry_asset_turnover()
        print(result.to_string())
