import logging
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from defeatbeta_api import HuggingFaceClient
from defeatbeta_api.client.duckdb_client import get_duckdb_client
from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.data.sql.sql_loader import load_sql
from defeatbeta_api.data.ticker import Ticker
from defeatbeta_api.utils.const import stock_profile


MAX_PARALLEL_SYMBOLS = 5


def select_symbols(primary, candidates, limit=MAX_PARALLEL_SYMBOLS):
    if limit < 1:
        raise ValueError("The symbol limit must be positive")
    peers = sorted({
        symbol for symbol in candidates
        if isinstance(symbol, str) and symbol != primary
    })
    return [primary, *peers[:limit - 1]]


@unittest.skipUnless(
    os.environ.get("DEFEATBETA_RUN_NETWORK_TESTS") == "1",
    "Set DEFEATBETA_RUN_NETWORK_TESTS=1 to run live concurrency checks",
)
class TestTickerMultithreaded(unittest.TestCase):

    def test_info(self):
        proxy = os.environ.get("DEFEATBETA_TEST_HTTP_PROXY")
        with tempfile.TemporaryDirectory() as directory:
            config = Configuration(cache_directory=directory)

            def run_test():
                ticker = Ticker(
                    "BABA", http_proxy=proxy, log_level=logging.WARNING,
                    config=config,
                )
                return ticker.info()

            with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SYMBOLS) as executor:
                results = list(executor.map(lambda _: run_test(), range(10)))

            self.assertFalse(results[0].empty)
            for result in results[1:]:
                pd.testing.assert_frame_equal(result, results[0])

            client = get_duckdb_client(
                http_proxy=proxy, log_level=logging.WARNING, config=config,
            )
            try:
                self.assertGreater(client._dataset_fs.metrics()["range_requests"], 0)
                self.assertFalse(list(Path(directory).glob(".partial-*")))
            finally:
                client.close()

    def test_download_data_performance(self):
        t = "BABA"
        proxy = os.environ.get("DEFEATBETA_TEST_HTTP_PROXY")
        ticker = Ticker(t, http_proxy=proxy, log_level=logging.DEBUG)
        info = ticker.info()
        industry = info['industry']
        if isinstance(industry, pd.Series):
            industry = industry.iloc[0]

        huggingface_client = HuggingFaceClient()
        url = huggingface_client.get_url_path(stock_profile)
        sql = load_sql("select_tickers_by_industry", url=url, industry=industry)
        duckdb_client = get_duckdb_client(
            http_proxy=proxy, log_level=logging.DEBUG, config=Configuration()
        )
        symbols = select_symbols(t, duckdb_client.query(sql)["symbol"])
        print(symbols)

        def run_test(symbol):
            tk = Ticker(
                symbol, http_proxy=proxy, log_level=logging.DEBUG,
                config=Configuration(),
            )
            market_cap = tk.market_capitalization()
            print(market_cap)

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SYMBOLS) as executor:
            list(executor.map(run_test, symbols))
