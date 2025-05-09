import sys

import duckdb
import logging
import time
import pandas as pd
from contextlib import contextmanager
from typing import Optional
from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api import data_update_time

from threading import Lock

_instance = None
_lock = Lock()

def get_duckdb_client(http_proxy=None, log_level=None, config=None):
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = DuckDBClient(http_proxy, log_level, config)
    return _instance

class DuckDBClient:
    def __init__(self, http_proxy: Optional[str] = None, log_level: Optional[str] = logging.INFO,
                 config: Optional[Configuration] = None):
        self.connection = None
        self.http_proxy = http_proxy
        self.config = config if config is not None else Configuration()
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s %(levelname)s %(name)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            stream=sys.stdout
        )
        self.logger = logging.getLogger(self.__class__.__name__)
        self._initialize_connection()
        self._validate_httpfs_cache()

    def _initialize_connection(self) -> None:
        try:
            self.connection = duckdb.connect(":memory:")
            self.logger.debug("DuckDB connection initialized.")

            duckdb_settings = self.config.get_duckdb_settings()
            if self.http_proxy:
                duckdb_settings.append(f"SET GLOBAL http_proxy = '{self.http_proxy}';")

            for query in duckdb_settings:
                self.logger.debug(f"DuckDB settings: {query}")
                self.connection.execute(query)
        except Exception as e:
            self.logger.error(f"Failed to initialize connection: {str(e)}")
            raise

    def _validate_httpfs_cache(self):
        try:
            current_spec = self.query(
                "SELECT * FROM 'https://huggingface.co/datasets/bwzheng2010/yahoo-finance-data/resolve/main/spec.json'"
            )
            current_update_time = current_spec['update_time'].dt.strftime('%Y-%m-%d').iloc[0]
            if current_update_time != data_update_time:
                self.logger.debug(f"Current update time: {current_update_time}, Remote update time: {data_update_time}")
                self.query(
                    "SELECT cache_httpfs_clear_cache()"
                )
        except Exception as e:
            self.logger.error(f"Failed to validate httpfs cache: {str(e)}")
            raise

    @contextmanager
    def _get_cursor(self):
        cursor = self.connection.cursor()
        try:
            yield cursor
        finally:
            cursor.close()

    def query(self, sql: str) -> pd.DataFrame:
        self.logger.debug(f"Executing query: {sql}")
        try:
            start_time = time.perf_counter()
            with self._get_cursor() as cursor:
                result = cursor.sql(sql).df()
                end_time = time.perf_counter()
                duration = end_time - start_time
                self.logger.debug(
                    f"Query executed successfully. Rows returned: {len(result)}. Cost: {duration:.2f} seconds.")
                return result
        except Exception as e:
            self.logger.error(f"Query failed: {str(e)}")
            raise Exception(f"Query failed: {str(e)}")

    def close(self) -> None:
        if self.connection:
            self.connection.close()
            self.logger.debug("DuckDB connection closed.")
            self.connection = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
