import logging
import unittest

from defeatbeta_api.data.company_meta import CompanyMeta


class TestCompanyMeta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        options = {
            "http_proxy": "http://127.0.0.1:8118",
            "log_level": logging.DEBUG,
        }
        cls.company_meta = CompanyMeta(**options)
        cls.us_company_meta = CompanyMeta(market="US", **options)
        cls.hk_company_meta = CompanyMeta(market="HK", **options)

    def test_company_tickers_url_uses_us_market_directory(self):
        self.assertEqual(
            self.company_meta.COMPANY_TICKERS_URL,
            "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/resolve/main/data/US/company_tickers.json"
        )
        self.assertEqual(
            self.us_company_meta.company_tickers_url,
            "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/resolve/main/data/US/company_tickers.json",
        )

    def test_hk_company_tickers_url_uses_hk_market_directory(self):
        self.assertEqual(
            self.hk_company_meta.company_tickers_url,
            "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/resolve/main/data/HK/company_tickers.json",
        )

    def test_get_company_info(self):
        result = self.company_meta.get_company_info("AAPL")
        print(f"Company Info: {result}")
        self.assertIsNotNone(result)
        self.assertEqual(result["symbol"], "AAPL")
        self.assertEqual(result["cik"], 320193)
        self.assertEqual(result["name"], "Apple Inc.")
        self.assertEqual(result["financial_currency"], "USD")
        self.assertEqual(set(result), {"idx", "symbol", "cik", "name", "financial_currency"})

    def test_get_hk_company_info(self):
        expected = {
            "0700.HK": ("KYG875721634", "TENCENT", "CNY"),
            "9988.HK": ("KYG017191142", "BABA-W", "CNY"),
            "1299.HK": ("HK0000069689", "AIA", "USD"),
        }

        for symbol, (isin, name, currency) in expected.items():
            with self.subTest(symbol=symbol):
                result = self.hk_company_meta.get_company_info(symbol)
                self.assertIsNotNone(result)
                self.assertEqual(result["symbol"], symbol)
                self.assertEqual(result["isin"], isin)
                self.assertEqual(result["name"], name)
                self.assertEqual(result["financial_currency"], currency)
                self.assertEqual(
                    set(result),
                    {"idx", "symbol", "isin", "name", "financial_currency"},
                )

    def test_get_financial_currency_map(self):
        result = self.company_meta.get_financial_currency_map()
        print(f"Total symbols: {len(result)}")
        self.assertIsNotNone(result)
        self.assertGreater(len(result), 0)
        self.assertEqual(result.get("AAPL"), "USD")

    def test_hk_financial_currency_map_preserves_missing_values(self):
        companies = self.hk_company_meta.get_all_companies_info()
        expected = {
            company["symbol"]: company["financial_currency"]
            for company in companies
        }
        result = self.hk_company_meta.get_financial_currency_map()

        self.assertEqual(result, expected)
        for symbol, currency in expected.items():
            if currency is None:
                self.assertIsNone(result[symbol])

    def test_get_all_companies_info(self):
        result = self.company_meta.get_all_companies_info()
        print(f"Total companies: {len(result)}")
        self.assertIsNotNone(result)
        self.assertGreater(len(result), 0)
        self.assertEqual(
            set(result[0]),
            {"idx", "symbol", "cik", "name", "financial_currency"},
        )

    def test_get_all_hk_companies_info(self):
        result = self.hk_company_meta.get_all_companies_info()

        self.assertGreater(len(result), 0)
        self.assertEqual(
            set(result[0]),
            {"idx", "symbol", "isin", "name", "financial_currency"},
        )

    def test_hk_ticker_universe_contains_only_required_company_examples(self):
        tickers = set(self.hk_company_meta.get_all_tickers())

        self.assertTrue({"0700.HK", "9988.HK", "1299.HK"}.issubset(tickers))
        self.assertTrue(
            {
                "0823.HK",
                "2800.HK",
                "4332.HK",
                "6288.HK",
                "80700.HK",
                "82800.HK",
                "9001.HK",
            }.isdisjoint(tickers)
        )

    def test_market_name_is_case_insensitive(self):
        company_meta = CompanyMeta(
            market="hk",
            http_proxy="http://127.0.0.1:8118",
            log_level=logging.DEBUG,
        )

        self.assertEqual(company_meta.market, "HK")

    def test_unsupported_market_raises_value_error(self):
        with self.assertRaisesRegex(ValueError, "Unsupported market"):
            CompanyMeta(market="JP")
