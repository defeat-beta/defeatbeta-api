import pandas as pd

from defeatbeta_api.data.ticker import Ticker


def get_stock_price(symbol: str, start_date: str = None, end_date: str = None):
    """
    Retrieve historical stock price data for the specified symbol and optional date range.

    Args:
        symbol: Stock ticker symbol, e.g., "TSLA", "AAPL" (case-insensitive).
        start_date: Optional start date in YYYY-MM-DD format (e.g., "2015-12-30").
                    If None, data starts from the earliest available date.
        end_date: Optional end date in YYYY-MM-DD format (e.g., "2025-12-24").
                  If None, data goes up to the most recent trading day.

    Returns:
        A dictionary with:
        - symbol
        - date_range (actual dates covered)
        - rows_returned (number of rows in this response)
        - truncated (True if data was limited by MAX_ROWS)
        - latest_close
        - data (list of daily records)

    Important note on data limits:
        To prevent responses from becoming too large for the language model to process
        (which can cause errors or token limit exceeded issues), this tool caps the
        maximum number of rows returned at 1000 (MAX_ROWS = 1000).
        When the requested range contains more than 1000 rows, only the most recent
        1000 trading days are returned, and "truncated": true is set.

        If you need data further back:
        - Make multiple calls with different (earlier) date ranges
        - Or call with a narrower start_date/end_date to stay under the limit
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)
    df = ticker.price()

    if df.empty:
        return {
            "symbol": symbol,
            "message": "No historical data available for this symbol."
        }

    # Convert and sort by date
    df['report_date'] = pd.to_datetime(df['report_date'])
    df = df.sort_values('report_date').reset_index(drop=True)

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
    data_records = df[['report_date', 'open', 'high', 'low', 'close', 'volume']].copy()
    data_records['report_date'] = data_records['report_date'].dt.strftime('%Y-%m-%d')

    return {
        "symbol": symbol,
        "date_range": f"{df['report_date'].min().date()} to {df['report_date'].max().date()}",
        "rows_returned": len(df),
        "truncated": truncated,
        "latest_close": float(df['close'].iloc[-1]),
        "data": data_records.to_dict(orient="records")
    }