import logging
import unittest

from defeatbeta_api.data.company_meta import CompanyMeta


class TestCompanyMeta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.company_meta = CompanyMeta(http_proxy="http://127.0.0.1:8118", log_level=logging.DEBUG)

    def test_get_company_info(self):
        result = self.company_meta.get_company_info("AAPL")
        print(f"Company Info: {result}")
        self.assertIsNotNone(result)
        self.assertEqual(result["symbol"], "AAPL")

    def test_get_financial_currency_map(self):
        result = self.company_meta.get_financial_currency_map()
        print(f"Total symbols: {len(result)}")
        self.assertIsNotNone(result)
        self.assertGreater(len(result), 0)
        self.assertEqual(result.get("AAPL"), "USD")

    def test_get_all_companies_info(self):
        result = self.company_meta.get_all_companies_info()
        print(f"Total companies: {len(result)}")
        self.assertIsNotNone(result)
        self.assertGreater(len(result), 0)
        self.assertIn("symbol", result[0])
        self.assertIn("cik", result[0])
        self.assertIn("name", result[0])
        self.assertIn("financial_currency", result[0])
