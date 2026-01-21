from .util import create_ticker


def get_stock_officers(symbol: str):
    """
    Retrieve key executive officers and senior management information
    for a given publicly traded company.

    This tool returns a list of company officers, including executives
    and senior leaders, along with their titles, age, compensation,
    and equity-related information when available.

    Args:
        symbol (str): Stock ticker symbol (e.g., "TSLA", "AAPL").
                      Case-insensitive and will be converted to uppercase.

    Returns:
        dict: A dictionary with the following structure:
            {
                "symbol": "TSLA",
                "rows_returned": 10,
                "officers": [
                    {
                        "name": "Mr. Elon R. Musk",
                        "title": "Co-Founder, Technoking of Tesla, CEO & Director",
                        "age": 53,
                        "born": 1971,
                        "pay": null,
                        "exercised": 0,
                        "unexercised": 0
                    },
                    ...
                ]
            }

    Notes:
        - Data is sourced from the defeatbeta dataset via `ticker.officers()`.
        - Missing or unavailable numeric values are returned as `null`.
        - Equity-related fields:
            - exercised: Number of stock options exercised
            - unexercised: Number of stock options unexercised
        - The list may include both executive officers and senior managers,
          depending on company disclosure.
        - If no officer data is available, an empty list is returned.
    """
    symbol = symbol.upper()
    ticker = create_ticker(symbol)
    df = ticker.officers()

    if df.empty:
        return {
            "symbol": symbol,
            "rows_returned": 0,
            "officers": []
        }

    # Select and normalize fields for LLM-friendly JSON output
    officers_df = df[
        ["name", "title", "age", "born", "pay", "exercised", "unexercised"]
    ].copy()

    # Convert pandas NA to None for clean JSON serialization
    officers_df = officers_df.where(officers_df.notna(), None)

    return {
        "symbol": symbol,
        "rows_returned": len(officers_df),
        "officers": officers_df.to_dict(orient="records")
    }
