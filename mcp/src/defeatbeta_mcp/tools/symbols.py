from defeatbeta_api.utils.util import load_financial_currency


def get_supported_symbols():
    """
    Get all supported stock symbols in the defeatbeta dataset.

    This function returns a list of all stock symbols that have financial data
    available in the dataset. Use this to check if a particular symbol is supported
    before querying other financial data.

    Returns:
        A dictionary containing:
        - total_count: The total number of supported symbols
        - symbols: A sorted list of all supported stock symbols (e.g., ["AAPL", "GOOGL", "MSFT", ...])
        - note: A description of what this data represents
    """
    currency_map = load_financial_currency()
    symbols = sorted(currency_map.keys())
    return {
        "total_count": len(symbols),
        "symbols": symbols,
        "note": "This is the list of all stock symbols with financial data available in the defeatbeta dataset."
    }
