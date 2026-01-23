import pandas as pd

from .util import create_ticker


def get_stock_wacc(symbol: str, start_date: str = None, end_date: str = None):
    """
    Retrieve historical Weighted Average Cost of Capital (WACC) data for a given stock symbol.

    WACC = Weight of Debt × Cost of Debt × (1 - Tax Rate) + Weight of Equity × Cost of Equity

    Where:
        Weight of Debt   = Total Debt / (Total Debt + Market Capitalization)
        Cost of Debt     = Interest Expense / Total Debt
        Weight of Equity = Market Capitalization / (Total Debt + Market Capitalization)
        Cost of Equity   = Risk-Free Rate + Beta × (Expected Market Return - Risk-Free Rate)

    Args:
        symbol (str):
            Stock ticker symbol, e.g., "TSLA", "AAPL" (case-insensitive).

        start_date (str, optional):
            Start date in YYYY-MM-DD format.
            Filters data where report_date >= start_date.
            If None, data starts from the earliest available date.

        end_date (str, optional):
            End date in YYYY-MM-DD format.
            Filters data where report_date <= end_date.
            If None, data goes up to the most recent trading day.

    Returns:
        dict: {
            "symbol": str,
            "date_range": str,                            # Actual date range returned
            "rows_returned": int,                         # Number of rows
            "truncated": bool,                            # True if rows were truncated due to MAX_ROWS
            "data": list[dict],                           # List of records with:
                - report_date (str):                      # Date of observation
                - market_capitalization (decimal):        # Market capitalization in USD
                - total_debt (decimal):                   # Total debt converted to USD
                - interest_expense (decimal):             # Interest expense converted to USD
                - tax_rate_for_calcs (decimal):           # Effective tax rate used for calculation
                - expected_market_return (decimal):       # 10-year rolling CAGR of S&P 500
                - risk_free_rate (decimal):               # 10-Year U.S. Treasury yield
                - beta_5y (decimal):                      # 5-year rolling beta
                - weight_of_debt (decimal):               # Total Debt / (Total Debt + Market Cap)
                - weight_of_equity (decimal):             # Market Cap / (Total Debt + Market Cap)
                - cost_of_debt (decimal):                 # Interest Expense / Total Debt
                - cost_of_equity (decimal):               # Risk-Free Rate + Beta × (Market Return - Risk-Free Rate)
                - wacc (decimal):                         # Weighted Average Cost of Capital
        }

    Important note on data limits:
        To prevent responses from becoming too large for the language model to process
        (which can cause errors or token limit exceeded issues), this tool caps the
        maximum number of rows returned at 1000 (MAX_ROWS = 1000).
        When the requested range contains more than 1000 rows, only the most recent
        1000 trading days are returned, and "truncated": true is set.

        If you need data further back:
        - Make multiple calls with different (earlier) date ranges
        - Or call with a narrower start_date/end_date to stay under the limit

    Note:
        Unless explicitly stated otherwise, this tool operates on data that is
        current up to the latest data update date returned by
        `get_latest_data_update_date`. Use that date as the authoritative
        reference point ("today") when interpreting date ranges or relative
        time expressions.
    """

    symbol = symbol.upper()
    ticker = create_ticker(symbol)
    df = ticker.wacc()

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
        df[['report_date', 'market_capitalization', 'total_debt_usd', 'interest_expense_usd',
            'tax_rate_for_calcs', 'sp500_10y_cagr', 'treasure_10y_yield', 'beta_5y',
            'weight_of_debt', 'weight_of_equity', 'cost_of_debt', 'cost_of_equity', 'wacc']]
        .copy()
        .rename(columns={
            'total_debt_usd': 'total_debt',
            'interest_expense_usd': 'interest_expense',
            'sp500_10y_cagr': 'expected_market_return',
            'treasure_10y_yield': 'risk_free_rate'
        })
    )
    data_records['report_date'] = data_records['report_date'].dt.strftime('%Y-%m-%d')

    return {
        "symbol": symbol,
        "date_range": f"{df['report_date'].min().date()} to {df['report_date'].max().date()}",
        "rows_returned": len(df),
        "truncated": truncated,
        "data": data_records.to_dict(orient="records")
    }
