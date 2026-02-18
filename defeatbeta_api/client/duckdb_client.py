import json
import logging
import os
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
        """Validate httpfs cache against remote data; clear cache if outdated.

        The remote update_time is fetched via plain HTTP (HuggingFaceClient).
        The locally cached update_time is read directly from the spec.json file
        that cache_httpfs already wrote to disk — bypassing DuckDB entirely.
        This eliminates the cross-process file-lock conflict that occurred when
        multiple processes shared the same cache_httpfs directory.
        """
        spec_url = "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/resolve/main/spec.json"

        try:
            remote_update_time = HuggingFaceClient().get_data_update_time()
            cached_update_time = self._read_cached_spec_update_time()

            if cached_update_time == remote_update_time:
                self.logger.info(f"Cache is up-to-date. Update time: {cached_update_time}")
            else:
                self.logger.info(
                    f"Cache outdated. Cached: {cached_update_time}, Remote: {remote_update_time}. "
                    f"Clearing cache..."
                )
                self._clear_cache()
                # Re-download spec.json via DuckDB so the cache file is repopulated
                # and the next startup can read it directly again.
                self.query(f"SELECT * FROM '{spec_url}'")
                self.logger.info(f"Cache refreshed. Update time: {remote_update_time}")

        except Exception as e:
            self.logger.error(f"Failed to validate httpfs cache: {str(e)}")
            raise

    def _read_cached_spec_update_time(self) -> Optional[str]:
        """Read update_time directly from the spec.json file on disk, bypassing DuckDB.

        cache_httpfs names cached files as:
            {url_hash}-{filename}-{start_byte}-{end_byte}
        We scan the cache directory for any file with 'spec.json' in its name
        and parse it as JSON.  Returns None when the file is absent or unreadable
        (e.g. first run, or corrupted by a killed write).
        """
        cache_dir = validate_httpfs_cache_directory()
        try:
            for filename in os.listdir(cache_dir):
                if 'spec.json' in filename:
                    try:
                        with open(os.path.join(cache_dir, filename), 'r') as f:
                            data = json.loads(f.read())
                        update_time = data.get('update_time')
                        if update_time:
                            self.logger.debug(f"Read cached update_time from {filename}: {update_time}")
                            return update_time
                    except Exception as e:
                        self.logger.debug(f"Could not read cached spec.json ({filename}): {e}")
                        continue
        except OSError:
            pass
        return None

    def _clear_cache(self):
        """Clear httpfs cache via DuckDB API."""
        self.query("SELECT cache_httpfs_clear_cache()")
        self.logger.info("httpfs cache cleared")

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
