import logging
import unittest

from defeatbeta_api.client.duckdb_client import DuckDBClient
from defeatbeta_api.client.duckdb_client import Configuration


class TestDuckDBClient(unittest.TestCase):

    def test_project_cache_defaults_are_bounded(self):
        config = Configuration(threads=8)
        self.assertEqual(config.cache_max_memory_blocks, 64)
        self.assertEqual(config.cache_max_disk_bytes, 1024 * 1024 * 1024)
        self.assertEqual(config.cache_workers, 3)

    def test_query(self):
        client = DuckDBClient(
            http_proxy="http://127.0.0.1:8118", log_level=logging.WARNING, config=Configuration(threads=8)
        )
        try:
            result = client.query(
                "SELECT * FROM 'https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/resolve/main/data/US/stock_prices.parquet' WHERE symbol = 'BABA'"
            )
            self.assertFalse(result.empty)
            result = client.query(
                "SELECT symbol,fiscal_year,fiscal_quarter,report_date,unnest(transcripts).paragraph_number as paragraph_number,unnest(transcripts).speaker as speaker,unnest(transcripts).content as content from 'https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/resolve/main/data/US/stock_earning_call_transcripts.parquet' where symbol='BABA' and fiscal_year=2025 and fiscal_quarter=2;"
            )
            self.assertFalse(result.empty)
            self.assertGreater(client._dataset_fs.metrics()["range_requests"], 0)
        finally:
            client.close()
