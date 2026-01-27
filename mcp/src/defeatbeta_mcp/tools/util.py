import os
from typing import Optional

from defeatbeta_api.data.ticker import Ticker
from defeatbeta_api.data.company_meta import CompanyMeta


def get_currency(symbol: str, default: str = "USD") -> str:
    company_meta = create_company_meta()
    info = company_meta.get_company_info(symbol)
    if info is None or info.get("financial_currency") is None:
        return default
    return info["financial_currency"]

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


def create_company_meta() -> CompanyMeta:
    proxy = get_http_proxy()

    if proxy:
        return CompanyMeta(http_proxy=proxy)

    return CompanyMeta()