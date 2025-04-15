import unittest
import pandas as pd

from client.duckdb_client import DuckDBClient

class TestDuckDBClient(unittest.TestCase):

    def test_query(self):
        client = DuckDBClient(
            http_proxy="http://127.0.0.1:33210"
        )
        try:
            result = client.query(
                "SELECT * FROM 'https://huggingface.co/datasets/bwzheng2010/yahoo-finance-data/resolve/main/data/stock_prices.parquet' WHERE symbol = 'BABA'"
            )
            with pd.option_context('display.max_rows', None,
                                   'display.max_columns', None,
                                   'display.width', None):
                print(result)
            result = client.query(
                "SELECT * FROM cache_httpfs_cache_access_info_query()"
            )
            print(result)
        finally:
            client.close()