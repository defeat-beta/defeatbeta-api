import logging
from typing import Optional

import pandas as pd

from defeatbeta_api import HuggingFaceClient
from defeatbeta_api.client.duckdb_client import get_duckdb_client
from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.utils.const import daily_treasury_yield


class Treasure:
    def __init__(self, http_proxy: Optional[str] = None, log_level: Optional[str] = logging.INFO, config: Optional[Configuration] = None):
        self.http_proxy = http_proxy
        self.duckdb_client = get_duckdb_client(http_proxy=self.http_proxy, log_level=log_level, config=config)
        self.huggingface_client = HuggingFaceClient()
        self.log_level = log_level

    def daily_treasure_yield(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(daily_treasury_yield)
        sql = f"SELECT * FROM '{url}'"
        return self.duckdb_client.query(sql)