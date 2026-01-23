from defeatbeta_api.utils.util import (
    load_sp500_historical_annual_returns as _load_sp500_historical_annual_returns,
    sp500_cagr_returns as _sp500_cagr_returns,
    sp500_cagr_returns_rolling as _sp500_cagr_returns_rolling,
)


def get_sp500_historical_annual_returns():
    """
    Retrieve historical annual returns for the S&P 500 index.

    This provides year-by-year total returns (including dividends) for the S&P 500,
    useful for understanding historical market performance.

    Returns:
        dict: {
            "date_range": str,           # Year range (e.g., "1928 to 2024")
            "rows_returned": int,        # Number of years returned
            "data": list[dict],          # List of records with:
                - year (int):            # Calendar year
                - annual_return (float): # Total return for that year (e.g., 0.1234 = 12.34%)
        }

    Note:
        Annual returns include both price appreciation and dividends reinvested.
        A return of 0.15 means a 15% gain; -0.10 means a 10% loss.
    """
    df = _load_sp500_historical_annual_returns()

    if df.empty:
        return {"message": "No S&P 500 historical data available."}

    df['year'] = df['report_date'].dt.year

    data_records = df[['year', 'annual_returns']].copy()
    data_records = data_records.rename(columns={'annual_returns': 'annual_return'})
    data_records['year'] = data_records['year'].astype(int)

    return {
        "date_range": f"{df['year'].min()} to {df['year'].max()}",
        "rows_returned": len(df),
        "data": data_records.to_dict(orient="records")
    }


def get_sp500_cagr_returns(years: int):
    """
    Calculate the Compound Annual Growth Rate (CAGR) for the S&P 500 over the most recent N years.

    CAGR represents the mean annual growth rate over a specified period,
    assuming profits are reinvested at the end of each year.

    Args:
        years (int):
            Number of recent years to calculate CAGR over.
            For example, years=10 calculates the 10-year CAGR ending at the most recent year.

    Returns:
        dict: {
            "years": int,           # Number of years used
            "cagr_returns": float   # CAGR as decimal (e.g., 0.1107 = 11.07% annual return)
        }

    Example:
        >>> get_sp500_cagr_returns(10)
        {"years": 10, "cagr_returns": 0.1107}

    Note:
        This is useful for estimating expected market returns in DCF models or WACC calculations.
    """
    df = _sp500_cagr_returns(years)

    if df.empty:
        return {"message": f"Unable to calculate CAGR for {years} years."}

    record = df.iloc[0]
    return {
        "years": int(record["years"]),
        "cagr_returns": float(record["cagr_returns"])
    }


def get_sp500_cagr_returns_rolling(years: int):
    """
    Calculate rolling CAGR for the S&P 500 over all possible N-year windows.

    This provides a historical view of how N-year returns have varied over time,
    useful for understanding the range of possible long-term returns.

    Args:
        years (int):
            Window size in years for each rolling CAGR calculation.
            For example, years=10 calculates 10-year CAGR for each possible 10-year period.

    Returns:
        dict: {
            "years": int,            # Window size used
            "rows_returned": int,    # Number of rolling periods
            "data": list[dict],      # List of records with:
                - start_year (int):  # Starting year of the period
                - end_year (int):    # Ending year of the period
                - cagr_returns (float): # CAGR for that period (e.g., 0.1107 = 11.07%)
        }

    Example:
        >>> get_sp500_cagr_returns_rolling(10)
        Returns all 10-year rolling CAGRs from 1928-1937, 1929-1938, ..., to the most recent.

    Note:
        Useful for understanding the historical distribution of long-term returns
        and setting realistic expectations for future market performance.
    """
    df = _sp500_cagr_returns_rolling(years)

    if df.empty:
        return {"message": f"Unable to calculate rolling CAGR for {years} years."}

    cagr_col = f"cagr_returns_{years}_years"
    data_records = df[['start_year', 'end_year', cagr_col]].copy()
    data_records = data_records.rename(columns={cagr_col: 'cagr_returns'})

    return {
        "years": years,
        "rows_returned": len(df),
        "data": data_records.to_dict(orient="records")
    }
