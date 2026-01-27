import logging
from typing import Optional, Dict, List

import pandas as pd

from defeatbeta_api.client.duckdb_client import get_duckdb_client
from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.data.sql.sql_loader import load_sql


class CompanyMeta:
    COMPANY_TICKERS_URL = "https://huggingface.co/datasets/bwzheng2010/yahoo-finance-data/resolve/main/data/company_tickers.json"

    def __init__(self, http_proxy: Optional[str] = None, log_level: Optional[str] = logging.INFO, config: Optional[Configuration] = None):
        self.http_proxy = http_proxy
        self.duckdb_client = get_duckdb_client(http_proxy=self.http_proxy, log_level=log_level, config=config)
        self.log_level = log_level

    def _get_all_companies(self) -> pd.DataFrame:
        sql = load_sql("select_all_companies", url=self.COMPANY_TICKERS_URL)
        return self.duckdb_client.query(sql)

    def _get_company_by_symbol(self, symbol: str) -> pd.DataFrame:
        sql = load_sql("select_company_by_symbol", url=self.COMPANY_TICKERS_URL, symbol=symbol)
        return self.duckdb_client.query(sql)

    def get_company_info(self, symbol: str) -> Optional[dict]:
        df = self._get_company_by_symbol(symbol)
        if df.empty:
            return None
        row = df.iloc[0]
        return {
            "idx": row["idx"],
            "symbol": row["symbol"],
            "cik": row["cik"],
            "name": row["name"],
            "financial_currency": row["financial_currency"]
        }

    def get_financial_currency_map(self) -> Dict[str, str]:
        df = self._get_all_companies()
        return dict(zip(df["symbol"], df["financial_currency"].fillna("USD")))

    def get_all_companies_info(self) -> List[dict]:
        df = self._get_all_companies()
        return df.to_dict(orient="records")
