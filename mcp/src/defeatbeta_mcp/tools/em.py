import pandas as pd

from defeatbeta_api.data.ticker import Ticker


def get_stock_quarterly_equity_multiplier(symbol: str):
    """
        Retrieve historical Equity Multiplier data for a given stock symbol.

        [!WARN] Equity Multiplier does not apply to banks or other financial institutions,
        as their balance sheet structures and leverage dynamics are fundamentally different
        from non-financial companies.

        In DuPont Analysis, the Equity Multiplier can be derived from ROE and ROA:
        Equity Multiplier = ROE / ROA

        Args:
            symbol (str):
                Stock ticker symbol, e.g., "TSLA", "AAPL" (case-insensitive).

        Returns:
            dict: {
                "symbol": str,
                "period_type": "quarterly",           # Equity Multiplier is reported on a quarterly basis
                "periods": list[str],                 # List of fiscal period end dates
                "rows_returned": int,                 # Number of periods returned
                "data": list[dict],                   # List of records with:
                    - period (str):                   # Fiscal period end date
                    - roe (decimal):                  # Return on Equity (ROE)
                    - roa (decimal):                  # Return on Assets (ROA)
                    - equity_multiplier (decimal):    # Financial leverage measure
            }
    """

    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.equity_multiplier()
    df['report_date'] = (
        pd.to_datetime(df['report_date'], errors='coerce')
        .dt.strftime('%Y-%m-%d')
    )

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "roe": row.get("roe"),
            "roa": row.get("roa"),
            "equity_multiplier": row.get("equity_multiplier")
        })

    return {
        "symbol": symbol,
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }


def get_industry_quarterly_equity_multiplier(symbol: str):
    """
    Retrieve historical industry-level Equity Multiplier data
    for the industry to which a given stock symbol belongs.

    In DuPont Analysis, the Equity Multiplier can be derived from ROE and ROA:
        Industry Equity Multiplier = Industry ROE / Industry ROA

    Args:
    symbol (str):
        Stock ticker symbol, e.g., "TSLA", "AAPL" (case-insensitive).

    Returns:
        dict: {
            "symbol": str,
            "currency": str,                            # Reporting currency (e.g., "USD")
            "period_type": "quarterly",                 # Industry metrics are reported on a quarterly basis
            "periods": list[str],                       # List of fiscal period end dates
            "rows_returned": int,                       # Number of periods returned
            "data": list[dict],                         # List of records with:
                - period (str):                         # Fiscal period end date
                - industry (str):                       # Industry name
                - industry_roe (decimal):               # Industry Return on Equity
                - industry_roa (decimal):               # Industry Return on Assets
                - industry_equity_multiplier (decimal): # Industry Equity Multiplier, derived from DuPont Analysis
        }

    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.industry_equity_multiplier()
    df['report_date'] = (
        pd.to_datetime(df['report_date'], errors='coerce')
        .dt.strftime('%Y-%m-%d')
    )

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "industry": row.get("industry"),
            "industry_roe": row.get("industry_roe"),
            "industry_roa": row.get("industry_roa"),
            "industry_equity_multiplier": row.get("industry_equity_multiplier")
        })

    return {
        "symbol": symbol,
        "currency": "USD",
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }