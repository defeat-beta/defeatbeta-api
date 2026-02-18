import logging
import os
import shutil
import sys
import time
from contextlib import contextmanager
from threading import Lock
from typing import Optional

import duckdb
import pandas as pd

from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.client.hugging_face_client import HuggingFaceClient
from defeatbeta_api.utils.util import validate_httpfs_cache_directory

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
        self.log_level = log_level
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s %(levelname)s %(name)s %(threadName)s - %(message)s',
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

            if self.log_level and self.log_level == logging.DEBUG:
                duckdb_settings.append("CALL enable_logging('HTTP', level = 'DEBUG', storage = 'stdout')")

            for query in duckdb_settings:
                self.logger.debug(f"DuckDB settings: {query}")
                self.connection.execute(query)
        except Exception as e:
            self.logger.error(f"Failed to initialize connection: {str(e)}")
            raise

    def _validate_httpfs_cache(self):
        """Validate httpfs cache against remote data, clear cache if outdated or corrupted."""
        spec_url = "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/resolve/main/spec.json"

        try:
            # Get remote update_time via HTTP request (bypasses cache)
            remote_update_time = HuggingFaceClient().get_data_update_time()

            # Get cached update_time via DuckDB (may use httpfs cache).
            # If the cache is corrupted (e.g. process killed mid-write), clear the
            # cache directory and retry once so the client is self-healing.
            try:
                cached_spec = self.query(f"SELECT * FROM '{spec_url}'")
            except Exception as cache_err:
                self.logger.warning(
                    f"Cache read failed (possibly corrupted): {cache_err}; "
                    f"clearing cache directory and retrying..."
                )
                self._clear_cache_directory()
                cached_spec = self.query(f"SELECT * FROM '{spec_url}'")

            cached_update_time = cached_spec['update_time'].dt.strftime('%Y-%m-%d').iloc[0]

            # Compare and clear cache if outdated
            if cached_update_time != remote_update_time:
                self.logger.info(
                    f"Cache outdated. Cached: {cached_update_time}, Remote: {remote_update_time}"
                )
                self._clear_cache()

                # Re-fetch data to update cache with latest remote data
                self.logger.info("Refreshing cache with latest remote data...")
                refreshed_spec = self.query(f"SELECT * FROM '{spec_url}'")
                refreshed_update_time = refreshed_spec['update_time'].dt.strftime('%Y-%m-%d').iloc[0]

                # Verify the cache now contains the latest data
                if refreshed_update_time == remote_update_time:
                    self.logger.info(
                        f"Cache refreshed and verified successfully. Update time: {refreshed_update_time}"
                    )
                else:
                    self.logger.warning(
                        f"Cache refresh verification failed. Expected: {remote_update_time}, Got: {refreshed_update_time}"
                    )
            else:
                self.logger.info(f"Cache is up-to-date. Update time: {cached_update_time}")

        except Exception as e:
            self.logger.error(f"Failed to validate httpfs cache: {str(e)}")
            raise

    def _clear_cache(self):
        """Clear httpfs cache via DuckDB API."""
        self.query("SELECT cache_httpfs_clear_cache()")
        self.logger.info("httpfs cache cleared")

    def _clear_cache_directory(self):
        """Clear httpfs cache by deleting and recreating the cache directory.

        Used as a fallback when the cache is corrupted and cannot be cleared
        via the DuckDB API (e.g. after a process was killed mid-write).
        """
        cache_dir = validate_httpfs_cache_directory()
        shutil.rmtree(cache_dir, ignore_errors=True)
        os.makedirs(cache_dir, exist_ok=True)
        self.logger.info(f"httpfs cache directory cleared: {cache_dir}")

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
