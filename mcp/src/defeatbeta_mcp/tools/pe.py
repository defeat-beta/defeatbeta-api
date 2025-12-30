import pandas as pd

from defeatbeta_api.data.ticker import Ticker

def get_stock_ttm_pe(symbol: str, start_date: str = None, end_date: str = None):
    """
    Retrieve historical TTM P/E (price-to-earnings) ratio and related data for a given stock symbol.

    Args:
        symbol: Stock ticker symbol, e.g., "TSLA", "AAPL" (case-insensitive).
        start_date: Optional start date in YYYY-MM-DD format (e.g., "2015-12-30").
                    If None, data starts from the earliest available date.
        end_date: Optional end date in YYYY-MM-DD format (e.g., "2025-12-24").
                  If None, data goes up to the most recent trading day.

    Returns:
        dict: {
            "symbol": str,
            "date_range": str,            # Actual date range returned
            "rows_returned": int,         # Number of rows
            "truncated": bool,            # True if rows were truncated due to MAX_ROWS
            "data": list[dict],           # List of records with:
                - report_date (str):      # Date of stock price observation
                - eps_report_date (str):  # The fiscal quarter-end date of the latest earnings used to compute TTM EPS
                - close_price (decimal):  # Stock closing price on report_date
                - ttm_diluted_eps (decimal | None):  # Most recent four-quarter Diluted EPS
                - ttm_pe (decimal | None):           # P/E ratio = close_price / ttm_diluted_eps
        }
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)
    df = ticker.price()

    if df.empty:
        return {
            "symbol": symbol,
            "message": "No historical data available for this symbol."
        }
    df['report_date'] = pd.to_datetime(df['report_date'])

    # Apply date filters
    if start_date:
        try:
            start_dt = pd.to_datetime(start_date)
            df = df[df['report_date'] >= start_dt]
        except ValueError:
            return {"error": f"Invalid start_date format: '{start_date}'. Use YYYY-MM-DD."}

    if end_date:
        try:
            end_dt = pd.to_datetime(end_date)
            df = df[df['report_date'] <= end_dt]
        except ValueError:
            return {"error": f"Invalid end_date format: '{end_date}'. Use YYYY-MM-DD."}

    if df.empty:
        return {
            "symbol": symbol,
            "message": "No data found for the specified date range."
        }

    # Safety cap to avoid token overflow in LLM context
    MAX_ROWS = 1000
    if len(df) > MAX_ROWS:
        df = df.tail(MAX_ROWS)  # Keep the newest rows
        truncated = True
    else:
        truncated = False

    # Format dates as strings for clean JSON
    data_records = (
        df[['report_date', 'eps_report_date', 'close_price', 'ttm_eps', 'ttm_pe']]
        .rename(columns={'ttm_eps': 'ttm_diluted_eps'})
        .copy()
    )
    data_records['report_date'] = data_records['report_date'].dt.strftime('%Y-%m-%d')

    return {
        "symbol": symbol,
        "date_range": f"{df['report_date'].min().date()} to {df['report_date'].max().date()}",
        "rows_returned": len(df),
        "truncated": truncated,
        "data": data_records.to_dict(orient="records")
    }