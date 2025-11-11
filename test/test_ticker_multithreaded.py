import logging
import unittest
import threading

import pandas as pd

from defeatbeta_api import HuggingFaceClient
from defeatbeta_api.client.duckdb_client import get_duckdb_client
from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.data.sql.sql_loader import load_sql
from defeatbeta_api.data.ticker import Ticker
from defeatbeta_api.utils.const import stock_profile


class TestTickerMultithreaded(unittest.TestCase):

    def test_info(self):
        def run_test():
            ticker = Ticker("BABA", http_proxy="http://127.0.0.1:33210", log_level=logging.DEBUG)
            result = ticker.info()
            print(f"Thread {threading.current_thread().name} result:\n{result.to_string()}")
            result = ticker.download_data_performance()
            print(result)

        threads = []
        for i in range(10):
            thread = threading.Thread(target=run_test, name=f"TestThread-{i}")
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

    def test_download_data_performance(self):
        t = "BABA"
        ticker = Ticker(t, http_proxy="http://127.0.0.1:33210", log_level=logging.DEBUG)
        info = ticker.info()
        industry = info['industry']
        if isinstance(industry, pd.Series):
            industry = industry.iloc[0]

        huggingface_client = HuggingFaceClient()
        url = huggingface_client.get_url_path(stock_profile)
        sql = load_sql("select_tickers_by_industry", url=url, industry=industry)
        duckdb_client = get_duckdb_client(http_proxy="http://127.0.0.1:33210", log_level=logging.DEBUG, config=Configuration())
        symbols = duckdb_client.query(sql)['symbol']
        symbols = symbols[symbols != t]
        symbols = pd.concat([pd.Series([t]), symbols], ignore_index=True)
        print(symbols.to_string())

        def run_test(symbol):
            tk = Ticker(symbol, http_proxy="http://127.0.0.1:33210", log_level=logging.DEBUG, config=Configuration())
            market_cap = tk.market_capitalization()
            print(market_cap)

        threads = []
        for symbol in symbols:
            thread = threading.Thread(target=run_test, args=(symbol,), name=f"TestThread-{symbol}")
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()