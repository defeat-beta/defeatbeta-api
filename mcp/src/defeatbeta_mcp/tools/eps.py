import pandas as pd

from defeatbeta_api.data.ticker import Ticker

def get_stock_eps_and_ttm_eps(symbol: str):
    """
    Retrieve quarterly EPS and trailing twelve months (TTM) EPS
    for a given stock symbol.

    This function returns a time-series dataset where each record
    represents a fiscal quarter, including:
    - EPS for the quarter
    - TTM EPS calculated up to that quarter

    Args:
        symbol (str): Stock ticker symbol (e.g. "TSLA", "AMD", "NVDA").

    Returns:
        dict: {
            "symbol": str,
            "currency": "USD",
            "rows_returned": int,
            "data": [
                {
                    "report_date": str,   # e.g. "2024-12-31"
                    "eps": decimal | None,  # quarterly EPS
                    "ttm_eps": decimal | None # Trailing Twelve Months EPS
                },
                ...
            ]
        }
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)
    df = ticker.ttm_eps()

    if df.empty:
        return {
            "symbol": symbol,
            "message": "No historical EPS or TTM EPS data available for this symbol."
        }

    df['report_date'] = pd.to_datetime(df['report_date'])
    data_records = (
        df[['report_date', 'eps', 'tailing_eps']]
        .rename(columns={'eps': 'diluted_eps', 'tailing_eps': 'ttm_diluted_eps'})
        .copy()
    )
    data_records['report_date'] = data_records['report_date'].dt.strftime('%Y-%m-%d')
    return {
        "symbol": symbol,
        "currency": "USD",
        "rows_returned": len(data_records),
        "data": data_records.to_dict(orient="records")
    }