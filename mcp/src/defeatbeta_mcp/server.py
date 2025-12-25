from mcp.server.fastmcp import FastMCP

from defeatbeta_api import data_update_time
from defeatbeta_api.data.ticker import Ticker
import pandas as pd

mcp = FastMCP(
    name="Defeat Beta API",
    instructions="An open-source alternative to Yahoo Finance's market data APIs with higher reliability.",
    website_url="https://github.com/defeat-beta/defeatbeta-api"
)

@mcp.tool()
def get_latest_data_update_date():
    """
        Get the latest data update date of the defeatbeta dataset.

        This is the most recent date for which historical price data is available
        in the defeatbeta dataset (typically the last date when the entire dataset
        was refreshed with new trading data).

        This is NOT the real-time server date, and NOT necessarily today's date.
        All available stock prices are up to and including trading days on or before
        this data date.

        Use this date as the reference point ("today" in data terms) when handling
        relative time queries such as "last 10 days", "past month", "year-to-date", etc.

        Returns:
            A dictionary containing the latest data date in YYYY-MM-DD format.
    """
    return {
        "latest_data_date": data_update_time,
        "note": "This is the latest DATA UPDATE DATE of the defeatbeta dataset. "
                "All historical price data available through this API is current "
                "up to this date. Use this date as the base for any relative time "
                "queries (e.g., 'recent 10 days' refers to the 10 trading days ending "
                "on or before this date)."
    }

@mcp.tool()
def get_stock_profile(symbol: str):
    """
        Retrieve the basic company profile information for a given stock symbol.

        Args:
            symbol (str): The stock ticker symbol, e.g., "TSLA" or "tsla" (will be automatically converted to uppercase).

        Returns:
            dict: A dictionary containing the company's basic profile information. Common keys include:
                - symbol: Stock ticker symbol
                - address: Company headquarters address
                - city: City where the company is headquartered
                - country: Country of headquarters
                - phone: Company phone number
                - zip: Postal/ZIP code
                - industry: Industry classification
                - sector: Sector classification
                - long_business_summary: Detailed business description/summary
                - full_time_employees: Number of full-time employees
                - web_site: Official company website URL
                - report_date: Date of the data report or last update

        Example (for TSLA):
            {
                'symbol': 'TSLA',
                'address': '1 Tesla Road',
                'city': 'Austin',
                'country': 'United States',
                'phone': '512 516 8177',
                'zip': '78725',
                'industry': 'Auto Manufacturers',
                'sector': 'Consumer Cyclical',
                'long_business_summary': 'Tesla, Inc. designs, develops, manufactures, l...',
                'full_time_employees': 125665,
                'web_site': 'https://www.tesla.com',
                'report_date': '2025-04-12'
            }

        Notes:
            - The underlying data is returned as a single-row pandas DataFrame from the ticker details.
            - The function converts the first row to a dictionary for easier handling.
            - If no data is available (empty DataFrame), an empty dictionary is returned.
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)
    df = ticker.info()
    # Convert the first row of the DataFrame to dict; return empty dict if no data
    profile = df.iloc[0].to_dict() if not df.empty else {}

    return profile

@mcp.tool()
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

def main():
    mcp.run()


if __name__ == "__main__":
    main()