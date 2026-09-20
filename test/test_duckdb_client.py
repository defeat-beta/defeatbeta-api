import logging
import unittest

import psutil

from defeatbeta_api.client.duckdb_client import DuckDBClient
from defeatbeta_api.client.duckdb_client import Configuration


class TestDuckDBClient(unittest.TestCase):

    def test_default_file_handle_cache_is_bounded(self):
        process = psutil.Process()
        handle_count = process.num_fds if hasattr(process, "num_fds") else process.num_handles
        config = Configuration(threads=8)
        client = DuckDBClient(
            http_proxy="http://127.0.0.1:8118", log_level=logging.WARNING, config=config
        )
        try:
            settings = client.query(
                "SELECT CAST(value AS INTEGER) AS value "
                "FROM duckdb_settings() "
                "WHERE name = 'cache_httpfs_file_handle_cache_entry_size'"
            )
            applied_cache_limit = int(settings.iloc[0]["value"])
            client.query("SELECT cache_httpfs_clear_cache()")
            stock_prices_query = (
                "SELECT SUM(close) FROM "
                "'https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/resolve/main/"
                "data/US/stock_prices.parquet'"
            )

            before = handle_count()
            client.query(stock_prices_query)
            after = handle_count()
            cold_cache_growth = after - before

            warm_before = handle_count()
            client.query(stock_prices_query)
            warm_after = handle_count()
            warm_cache_growth = warm_after - warm_before

            self.assertEqual(config.cache_httpfs_file_handle_cache_entry_size, 64)
            self.assertEqual(applied_cache_limit, 64)
            # The process also owns DuckDB, HTTP, and data-cache descriptors.
            max_process_handle_growth = applied_cache_limit * 2
            self.assertLessEqual(cold_cache_growth, max_process_handle_growth)
            self.assertLessEqual(warm_cache_growth, max_process_handle_growth)
        finally:
            client.close()

    def test_query(self):
        client = DuckDBClient(
            http_proxy="http://127.0.0.1:8118", log_level=logging.DEBUG, config=Configuration(threads=8)
        )
        try:
            result = client.query(
                "SELECT * FROM 'https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/resolve/main/data/US/stock_prices.parquet' WHERE symbol = 'BABA'"
            )
            print(result)
            result = client.query(
                "SELECT symbol,fiscal_year,fiscal_quarter,report_date,unnest(transcripts).paragraph_number as paragraph_number,unnest(transcripts).speaker as speaker,unnest(transcripts).content as content from 'https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/resolve/main/data/US/stock_earning_call_transcripts.parquet' where symbol='BABA' and fiscal_year=2025 and fiscal_quarter=2;"
            )
            print(result)
            result = client.query(
                "SELECT * FROM cache_httpfs_cache_access_info_query()"
            )
            print(result)
            result = client.query(
                "SELECT cache_httpfs_get_profile()"
            )
            print(result.to_string().replace('\\n', '\n'))
            result = client.query(
                "SELECT * from cache_httpfs_cache_status_query()"
            )
            print(result.to_string())
            result = client.query(
                "SELECT cache_httpfs_get_ondisk_data_cache_size()"
            )
            print(result.to_string())
        finally:
            client.close()
