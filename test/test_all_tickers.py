"""Optional live ticker checks without discovery-time network access."""

import logging
import os
import unittest

from defeatbeta_api.data.company_meta import CompanyMeta
from defeatbeta_api.data.ticker import Ticker


SAMPLE_SYMBOLS = ("AAPL", "PDD", "ZTS")


def _http_proxy():
    return os.environ.get("DEFEATBETA_TEST_HTTP_PROXY") or None


@unittest.skipUnless(
    os.environ.get("DEFEATBETA_RUN_NETWORK_TESTS") == "1",
    "Set DEFEATBETA_RUN_NETWORK_TESTS=1 to run live ticker checks",
)
class TestRepresentativeTickers(unittest.TestCase):
    def test_price_for_representative_symbols(self):
        for symbol in SAMPLE_SYMBOLS:
            with self.subTest(symbol=symbol):
                ticker = Ticker(symbol, http_proxy=_http_proxy(), log_level=logging.WARNING)
                self.assertFalse(ticker.price().empty)


@unittest.skipUnless(
    os.environ.get("DEFEATBETA_RUN_ALL_TICKERS") == "1",
    "Set DEFEATBETA_RUN_ALL_TICKERS=1 to run the exhaustive live check",
)
class TestAllTickers(unittest.TestCase):
    def test_price_for_every_us_symbol(self):
        meta = CompanyMeta(http_proxy=_http_proxy(), log_level=logging.WARNING)
        for symbol in meta.get_all_tickers():
            with self.subTest(symbol=symbol):
                ticker = Ticker(symbol, http_proxy=_http_proxy(), log_level=logging.WARNING)
                ticker.price()

if __name__ == "__main__":
    unittest.main()
