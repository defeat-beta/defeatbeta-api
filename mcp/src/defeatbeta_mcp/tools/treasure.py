import pandas as pd

from defeatbeta_api.data.treasure import Treasure


def get_daily_treasury_yield(start_date: str = None, end_date: str = None):
    """
    Retrieve daily U.S. Treasury yield curve rates for the optional date range.

    This provides historical daily yields for various Treasury maturities,
    useful for understanding interest rate environments and building discount rates.

    Args:
        start_date: Optional start date in YYYY-MM-DD format (e.g., "2020-01-01").
                    If None, data starts from the earliest available date.
        end_date: Optional end date in YYYY-MM-DD format (e.g., "2025-12-31").
                  If None, data goes up to the most recent date.

    Returns:
        dict: {
            "date_range": str,           # Date range (e.g., "1990-01-02 to 2025-09-19")
            "rows_returned": int,        # Number of days returned
            "truncated": bool,           # True if data was limited by MAX_ROWS
            "data": list[dict],          # List of records with:
                - report_date (str):     # Date in YYYY-MM-DD format
                - bc1_month (float):     # 1-month Treasury yield (e.g., 0.0422 = 4.22%)
                - bc2_month (float):     # 2-month Treasury yield
                - bc3_month (float):     # 3-month Treasury yield
                - bc6_month (float):     # 6-month Treasury yield
                - bc1_year (float):      # 1-year Treasury yield
                - bc2_year (float):      # 2-year Treasury yield
                - bc3_year (float):      # 3-year Treasury yield
                - bc5_year (float):      # 5-year Treasury yield
                - bc7_year (float):      # 7-year Treasury yield
                - bc10_year (float):     # 10-year Treasury yield
                - bc30_year (float):     # 30-year Treasury yield
        }

    Important note on data limits:
        To prevent responses from becoming too large for the language model to process
        (which can cause errors or token limit exceeded issues), this tool caps the
        maximum number of rows returned at 1000 (MAX_ROWS = 1000).
        When the requested range contains more than 1000 rows, only the most recent
        1000 days are returned, and "truncated": true is set.

        If you need data further back:
        - Make multiple calls with different (earlier) date ranges
        - Or call with a narrower start_date/end_date to stay under the limit

    Note:
        Yields are expressed as decimals (e.g., 0.0405 = 4.05%).
        Some maturities may have NaN values for earlier dates when those instruments were not issued.
        The 10-year Treasury yield is commonly used as the risk-free rate in financial models.
    """
    treasure = Treasure()
    df = treasure.daily_treasure_yield()

    if df.empty:
        return {"message": "No Treasury yield data available."}

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
        return {"message": "No data found for the specified date range."}

    # Safety cap to avoid token overflow in LLM context
    MAX_ROWS = 1000
    if len(df) > MAX_ROWS:
        df = df.tail(MAX_ROWS)  # Keep the newest rows
        truncated = True
    else:
        truncated = False

    # Format dates as strings for clean JSON
    df['report_date'] = df['report_date'].dt.strftime('%Y-%m-%d')

    return {
        "date_range": f"{df['report_date'].min()} to {df['report_date'].max()}",
        "rows_returned": len(df),
        "truncated": truncated,
        "data": df.to_dict(orient="records")
    }
