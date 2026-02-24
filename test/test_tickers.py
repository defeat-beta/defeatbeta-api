import logging
import unittest

import pandas as pd

from defeatbeta_api.data.news import News
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