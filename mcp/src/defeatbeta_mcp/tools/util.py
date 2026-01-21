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
        os.getenv("DEFEATBETA_GATEWAY")
        or os.getenv("defeatbeta_gateway")
    )

def create_ticker(symbol: str) -> Ticker:
    proxy = get_http_proxy()
    symbol = symbol.upper()

    if proxy:
        return Ticker(symbol, http_proxy=proxy)

    return Ticker(symbol)