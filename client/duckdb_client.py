import logging
import time
from contextlib import contextmanager
from typing import Optional, Dict, Any

import duckdb

from client.duckdb_conf import duckdb_settings


class DuckDBClient:
    """
    A robust DuckDB client for querying local and remote data with optimized configurations.
    """
    def __init__(self, http_proxy: Optional[str] = None):
        self.connection = None
        self.http_proxy = http_proxy
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("defeat-beta")
        self._initialize_connection()

    def _initialize_connection(self) -> None:
        try:
            self.connection = duckdb.connect(":memory:")
            self.logger.info("DuckDB connection initialized.")

            if self.http_proxy:
                duckdb_settings.append(f"SET http_proxy = '{self.http_proxy}';")

            for query in duckdb_settings:
                self.logger.info(f"duckdb settings: {query}")
                self.connection.execute(query)
        except Exception as e:
            self.logger.error(f"Failed to initialize connection: {str(e)}")
            raise

    @contextmanager
    def _get_cursor(self):
        """
        Context manager for DuckDB cursor to ensure proper resource management.
        """
        cursor = self.connection.cursor()
        try:
            yield cursor
        finally:
            cursor.close()

    def query(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Any:
        self.logger.info(f"Executing query: {sql}")
        try:
            start_time = time.perf_counter()
            with self._get_cursor() as cursor:
                if params:
                    result = cursor.sql(sql, params=params).df()
                else:
                    result = cursor.sql(sql).df()
                end_time = time.perf_counter()
                duration = end_time - start_time
                self.logger.info(f"Query executed successfully. Rows returned: {len(result)}. Cost: {duration:.2f} seconds.")
                return result
        except Exception as e:
            self.logger.error(f"Query failed: {str(e)}")
            raise Exception(f"Query failed: {str(e)}")

    def close(self) -> None:
        """
        Close the DuckDB connection.
        """
        if self.connection:
            self.connection.close()
            self.logger.info("DuckDB connection closed.")
            self.connection = None

    def __enter__(self):
        """
        Support for context manager to ensure connection is initialized.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Ensure connection is closed when exiting context.
        """
        self.close()