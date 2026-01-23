from defeatbeta_api.data.treasure import Treasure


def get_daily_treasury_yield():
    """
    Retrieve daily U.S. Treasury yield curve rates.

    This provides historical daily yields for various Treasury maturities,
    useful for understanding interest rate environments and building discount rates.

    Returns:
        dict: {
            "date_range": str,           # Date range (e.g., "1990-01-02 to 2025-09-19")
            "rows_returned": int,        # Number of days returned
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

    Note:
        Yields are expressed as decimals (e.g., 0.0405 = 4.05%).
        Some maturities may have NaN values for earlier dates when those instruments were not issued.
        The 10-year Treasury yield is commonly used as the risk-free rate in financial models.
    """
    treasure = Treasure()
    df = treasure.daily_treasure_yield()

    if df.empty:
        return {"message": "No Treasury yield data available."}

    df['report_date'] = df['report_date'].astype(str)

    return {
        "date_range": f"{df['report_date'].min()} to {df['report_date'].max()}",
        "rows_returned": len(df),
        "data": df.to_dict(orient="records")
    }
