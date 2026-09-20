import logging
from typing import Optional, Dict, List

import pandas as pd

from defeatbeta_api.client.duckdb_client import get_duckdb_client
from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.data.sql.sql_loader import load_sql


class CompanyMeta:
    COMPANY_TICKERS_URL = "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/resolve/main/data/US/company_tickers.json"
    _MARKETS = {
        "US": {
            "url": COMPANY_TICKERS_URL,
            "identifier_field": "cik_str",
            "identifier_type": "INTEGER",
            "identifier_alias": "cik",
        },
        "HK": {
            "url": "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/resolve/main/data/HK/company_tickers.json",
            "identifier_field": "isin",
            "identifier_type": "VARCHAR",
            "identifier_alias": "isin",
        },
    }

    def __init__(
        self,
        http_proxy: Optional[str] = None,
        log_level: Optional[str] = logging.INFO,
        config: Optional[Configuration] = None,
        market: str = "US",
    ):
        normalized_market = market.upper() if isinstance(market, str) else ""
        if normalized_market not in self._MARKETS:
            supported = ", ".join(sorted(self._MARKETS))
            raise ValueError(
                f"Unsupported market: {market!r}. Supported markets: {supported}"
            )

        market_config = self._MARKETS[normalized_market]
        self.market = normalized_market
        self.company_tickers_url = market_config["url"]
        self._identifier_field = market_config["identifier_field"]
        self._identifier_type = market_config["identifier_type"]
        self._identifier_alias = market_config["identifier_alias"]
        self.http_proxy = http_proxy
        self.duckdb_client = get_duckdb_client(http_proxy=self.http_proxy, log_level=log_level, config=config)
        self.log_level = log_level

    def _get_all_companies(self) -> pd.DataFrame:
        sql = load_sql(
            "select_all_companies",
            url=self.company_tickers_url,
            identifier_field=self._identifier_field,
            identifier_type=self._identifier_type,
            identifier_alias=self._identifier_alias,
        )
        return self.duckdb_client.query(sql)

    def _get_company_by_symbol(self, symbol: str) -> pd.DataFrame:
        sql = load_sql(
            "select_company_by_symbol",
            url=self.company_tickers_url,
            symbol=symbol,
            identifier_field=self._identifier_field,
            identifier_type=self._identifier_type,
            identifier_alias=self._identifier_alias,
        )
        return self.duckdb_client.query(sql)

    def get_company_info(self, symbol: str) -> Optional[dict]:
        df = self._get_company_by_symbol(symbol)
        if df.empty:
            return None
        row = df.iloc[0]
        return {
            "idx": row["idx"],
            "symbol": row["symbol"],
            self._identifier_alias: row[self._identifier_alias],
            "name": row["name"],
            "financial_currency": row["financial_currency"]
        }

    def get_financial_currency_map(self) -> Dict[str, Optional[str]]:
        df = self._get_all_companies()
        return dict(zip(df["symbol"], df["financial_currency"]))

    def get_all_companies_info(self) -> List[dict]:
        df = self._get_all_companies()
        return df.to_dict(orient="records")

    def get_all_tickers(self) -> List[str]:
        df = self._get_all_companies()
        return df["symbol"].tolist()
