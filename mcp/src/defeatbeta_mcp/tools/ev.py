import pandas as pd

from .util import create_ticker

MAX_ROWS = 1000


def _apply_date_filter(df: pd.DataFrame, start_date: str, end_date: str, symbol: str):
    if start_date:
        try:
            df = df[df['report_date'] >= pd.to_datetime(start_date)]
        except ValueError:
            return None, {"error": f"Invalid start_date format: '{start_date}'. Use YYYY-MM-DD."}
    if end_date:
        try:
            df = df[df['report_date'] <= pd.to_datetime(end_date)]
        except ValueError:
            return None, {"error": f"Invalid end_date format: '{end_date}'. Use YYYY-MM-DD."}
    if df.empty:
        return None, {"symbol": symbol, "message": "No data found for the specified date range."}
    return df, None


def get_stock_enterprise_value(symbol: str, start_date: str = None, end_date: str = None):
    """
    Retrieve historical Enterprise Value (EV) data for a given stock symbol.

    Enterprise Value = Market Capitalization + Total Debt + Minority Interest
                       + Preferred Stock Equity - Cash and Cash Equivalents
    All balance sheet components are converted to USD using the exchange rate
    on the corresponding report date.

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
            "currency": "USD",
            "date_range": str,                              # Actual date range returned
            "rows_returned": int,                           # Number of rows returned
            "truncated": bool,                              # True if rows were truncated due to MAX_ROWS
            "data": list[dict],                             # List of records with:
                - report_date (str):                        # Date of stock price observation
                - fiscal_quarter (str):                     # Fiscal quarter-end date of latest balance sheet used
                - market_capitalization (decimal):          # Market cap in USD on report_date
                - exchange_to_usd_rate (decimal):           # FX rate used to convert balance sheet items to USD
                - total_debt (decimal):                     # Total debt in reporting currency
                - total_debt_usd (decimal):                 # Total debt in USD
                - minority_interest (decimal):              # Minority interest in reporting currency
                - minority_interest_usd (decimal):          # Minority interest in USD
                - preferred_stock_equity (decimal):         # Preferred stock equity in reporting currency
                - preferred_stock_equity_usd (decimal):     # Preferred stock equity in USD
                - cash_and_cash_equivalents (decimal):      # Cash and equivalents in reporting currency
                - cash_and_cash_equivalents_usd (decimal):  # Cash and equivalents in USD
                - enterprise_value (decimal):               # Enterprise Value in USD
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
    df = ticker.enterprise_value()

    if df.empty:
        return {"symbol": symbol, "message": "No historical data available for this symbol."}

    df['report_date'] = pd.to_datetime(df['report_date'])
    df['fiscal_quarter'] = pd.to_datetime(df['fiscal_quarter'])

    df, err = _apply_date_filter(df, start_date, end_date, symbol)
    if err:
        return err

    truncated = False
    if len(df) > MAX_ROWS:
        df = df.tail(MAX_ROWS)
        truncated = True

    cols = [
        'report_date', 'fiscal_quarter', 'market_capitalization',
        'exchange_to_usd_rate',
        'total_debt', 'total_debt_usd',
        'minority_interest', 'minority_interest_usd',
        'preferred_stock_equity', 'preferred_stock_equity_usd',
        'cash_and_cash_equivalents', 'cash_and_cash_equivalents_usd',
        'enterprise_value'
    ]
    data_records = df[cols].copy()
    data_records['report_date'] = data_records['report_date'].dt.strftime('%Y-%m-%d')
    data_records['fiscal_quarter'] = data_records['fiscal_quarter'].dt.strftime('%Y-%m-%d')

    return {
        "symbol": symbol,
        "currency": "USD",
        "date_range": f"{df['report_date'].min().strftime('%Y-%m-%d')} to {df['report_date'].max().strftime('%Y-%m-%d')}",
        "rows_returned": len(df),
        "truncated": truncated,
        "data": data_records.to_dict(orient="records")
    }


def get_stock_enterprise_to_revenue(symbol: str, start_date: str = None, end_date: str = None):
    """
    Retrieve historical EV/Revenue ratio for a given stock symbol.

    EV/Revenue = Enterprise Value / Trailing Twelve Months (TTM) Revenue (in USD)

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
            "currency": "USD",
            "date_range": str,                   # Actual date range returned
            "rows_returned": int,                # Number of rows returned
            "truncated": bool,                   # True if rows were truncated due to MAX_ROWS
            "data": list[dict],                  # List of records with:
                - report_date (str):             # Date of stock price observation
                - fiscal_quarter (str):          # Fiscal quarter-end date of the latest TTM revenue calculation
                - enterprise_value (decimal):    # Enterprise Value in USD
                - ttm_revenue (decimal):         # TTM revenue in reporting currency
                - ttm_revenue_usd (decimal):     # TTM revenue in USD
                - ev_to_revenue (decimal):       # EV/Revenue = enterprise_value / ttm_revenue_usd
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
    df = ticker.enterprise_to_revenue()

    if df.empty:
        return {"symbol": symbol, "message": "No historical data available for this symbol."}

    df['report_date'] = pd.to_datetime(df['report_date'])
    df['fiscal_quarter'] = pd.to_datetime(df['fiscal_quarter'])

    df, err = _apply_date_filter(df, start_date, end_date, symbol)
    if err:
        return err

    truncated = False
    if len(df) > MAX_ROWS:
        df = df.tail(MAX_ROWS)
        truncated = True

    cols = ['report_date', 'fiscal_quarter', 'enterprise_value', 'ttm_revenue', 'ttm_revenue_usd', 'ev_to_revenue']
    data_records = df[cols].copy()
    data_records['report_date'] = data_records['report_date'].dt.strftime('%Y-%m-%d')
    data_records['fiscal_quarter'] = data_records['fiscal_quarter'].dt.strftime('%Y-%m-%d')

    return {
        "symbol": symbol,
        "currency": "USD",
        "date_range": f"{df['report_date'].min().strftime('%Y-%m-%d')} to {df['report_date'].max().strftime('%Y-%m-%d')}",
        "rows_returned": len(df),
        "truncated": truncated,
        "data": data_records.to_dict(orient="records")
    }


def get_stock_enterprise_to_ebitda(symbol: str, start_date: str = None, end_date: str = None):
    """
    Retrieve historical EV/EBITDA ratio for a given stock symbol.

    EV/EBITDA = Enterprise Value / Trailing Twelve Months (TTM) EBITDA (in USD)

    [!WARN]
    EV/EBITDA is generally NOT applicable to banks and other financial institutions,
    due to their fundamentally different balance sheet structures.

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
            "currency": "USD",
            "date_range": str,                   # Actual date range returned
            "rows_returned": int,                # Number of rows returned
            "truncated": bool,                   # True if rows were truncated due to MAX_ROWS
            "data": list[dict],                  # List of records with:
                - report_date (str):             # Date of stock price observation
                - fiscal_quarter (str):          # Fiscal quarter-end date of the latest TTM EBITDA calculation
                - enterprise_value (decimal):    # Enterprise Value in USD
                - ttm_ebitda (decimal):          # TTM EBITDA in reporting currency
                - ttm_ebitda_usd (decimal):      # TTM EBITDA in USD
                - ev_to_ebitda (decimal):        # EV/EBITDA = enterprise_value / ttm_ebitda_usd
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
    df = ticker.enterprise_to_ebitda()

    if df.empty:
        return {"symbol": symbol, "message": "No historical data available for this symbol."}

    df['report_date'] = pd.to_datetime(df['report_date'])
    df['fiscal_quarter'] = pd.to_datetime(df['fiscal_quarter'])

    df, err = _apply_date_filter(df, start_date, end_date, symbol)
    if err:
        return err

    truncated = False
    if len(df) > MAX_ROWS:
        df = df.tail(MAX_ROWS)
        truncated = True

    cols = ['report_date', 'fiscal_quarter', 'enterprise_value', 'ttm_ebitda', 'ttm_ebitda_usd', 'ev_to_ebitda']
    data_records = df[cols].copy()
    data_records['report_date'] = data_records['report_date'].dt.strftime('%Y-%m-%d')
    data_records['fiscal_quarter'] = data_records['fiscal_quarter'].dt.strftime('%Y-%m-%d')

    return {
        "symbol": symbol,
        "currency": "USD",
        "date_range": f"{df['report_date'].min().strftime('%Y-%m-%d')} to {df['report_date'].max().strftime('%Y-%m-%d')}",
        "rows_returned": len(df),
        "truncated": truncated,
        "data": data_records.to_dict(orient="records")
    }
