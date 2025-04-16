import logging
from typing import Optional

import pandas as pd

from client.duckdb_client import DuckDBClient
from client.duckdb_conf import Configuration
from client.hugging_face_client import HuggingFaceClient
from utils.const import stock_profile, stock_earning_calendar, stock_historical_eps, stock_officers, stock_split_events, \
    stock_dividend_events, stock_revenue_estimates, stock_earning_estimates, stock_summary, stock_tailing_eps, \
    stock_prices


class Ticker:
    def __init__(self, ticker, http_proxy: Optional[str] = None, log_level: Optional[str] = logging.INFO, config: Optional[Configuration] = None):
        self.ticker = ticker.upper()
        self.http_proxy = http_proxy
        self.duckdb_client = DuckDBClient(http_proxy=self.http_proxy, log_level=log_level, config=config)
        self.huggingface_client = HuggingFaceClient()

    def info(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_profile)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def officers(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_officers)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def calendar(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_earning_calendar)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def earnings(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_historical_eps)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def splits(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_split_events)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def dividends(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_dividend_events)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def revenue_forecast(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_revenue_estimates)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def earnings_forecast(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_earning_estimates)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def summary(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_summary)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def ttm_eps(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_tailing_eps)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def price(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_prices)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def download_data_performance(self) -> pd.DataFrame:
        return self.duckdb_client.query(
            "SELECT * FROM cache_httpfs_cache_access_info_query()"
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duckdb_client.close()

    def __del__(self):
        self.duckdb_client.close()
