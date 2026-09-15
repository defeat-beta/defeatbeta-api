import unittest

from defeatbeta_api.client.hugging_face_client import HuggingFaceClient

class TestHuggingFaceClient(unittest.TestCase):

    def test_get_url_path_uses_us_market_directory(self):
        client = HuggingFaceClient()

        self.assertEqual(
            client.get_url_path("stock_profile"),
            "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/resolve/main/data/US/stock_profile.parquet"
        )

    def test_get_url_path(self):
        client = HuggingFaceClient()
        url_path = client.get_url_path("stock_profile")
        print(url_path)
        data_update_time = client.get_data_update_time()
        print(data_update_time)
