import logging
import unittest

from defeatbeta_api.client.duckdb_client import DuckDBClient
from defeatbeta_api.client.duckdb_client import Configuration


class TestDuckDBClient(unittest.TestCase):

    def test_query(self):
        client = DuckDBClient(
            http_proxy="http://127.0.0.1:33210", log_level=logging.DEBUG, config=Configuration(threads=8)
        )
        try:
            result = client.query(
                "SELECT * FROM 'https://huggingface.co/datasets/bwzheng2010/yahoo-finance-data/resolve/main/data/stock_prices.parquet' WHERE symbol = 'BABA'"
            )
            print(result)
            result = client.query(
                "SELECT symbol,fiscal_year,fiscal_quarter,report_date,unnest(transcripts).paragraph_number as paragraph_number,unnest(transcripts).speaker as speaker,unnest(transcripts).content as content from 'https://huggingface.co/datasets/bwzheng2010/yahoo-finance-data/resolve/main/data/stock_earning_call_transcripts.parquet' where symbol='BABA' and fiscal_year=2025 and fiscal_quarter=2;"
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