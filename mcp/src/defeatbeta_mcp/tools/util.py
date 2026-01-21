import os
from typing import Optional

from defeatbeta_api.data.ticker import Ticker
from defeatbeta_api.utils.util import load_financial_currency


def get_currency(symbol: str, default: str = "USD") -> str:
    currency = load_financial_currency().get(symbol)
    if currency is None:
        currency = default
    return currency

def get_http_proxy() -> Optional[str]:
    return (
        os.getenv("HTTP_PROXY")
        or os.getenv("http_proxy")
        or os.getenv("HTTPS_PROXY")
        or os.getenv("https_proxy")
        or os.getenv("ALL_PROXY")
        or os.getenv("all_proxy")
    )

def create_ticker(symbol: str) -> Ticker:
    proxy = get_http_proxy()
    symbol = symbol.upper()

    if proxy:
        return Ticker(symbol, http_proxy=proxy)

    return Ticker(symbol)