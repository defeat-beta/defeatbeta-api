from defeatbeta_api.utils.util import load_financial_currency


def get_currency(symbol: str, default: str = "USD") -> str:
    currency = load_financial_currency().get(symbol)
    if currency is None:
        currency = default
    return currency