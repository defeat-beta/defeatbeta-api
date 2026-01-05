import pandas as pd

from defeatbeta_api.data.ticker import Ticker
from .util import get_currency


def get_stock_quarterly_roe(symbol: str):
    """
    Retrieve historical Return on Equity (ROE) data for a given stock symbol.

    Args:
        symbol (str):
            Stock ticker symbol, e.g., "TSLA", "AAPL" (case-insensitive).

    Returns:
        dict: {
            "symbol": str,
            "currency": str,                                 # Reporting currency (e.g., "USD")
            "period_type": "quarterly",                      # ROE is reported on quarterly basis
            "periods": list[str],                            # List of fiscal period end dates
            "rows_returned": int,                            # Number of periods returned
            "data": list[dict],                              # List of records with:
                - period (str):                              # Fiscal period end date
                - net_income_common_stockholders (decimal):  # Net income attributable to common stockholders
                - beginning_stockholders_equity (decimal):   # Stockholders' equity at the beginning of the period (i.e., prior period ending equity)
                - ending_stockholders_equity (decimal):      # Stockholders' equity at the end of the current period
                - avg_equity (decimal):                      # Average stockholders' equity = (beginning_stockholders_equity + ending_stockholders_equity) / 2
                - roe (decimal):                             # Return on Equity = net_income_common_stockholders / avg_equity
        }

    """

    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.roe()

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "net_income_common_stockholders": row.get("net_income_common_stockholders"),
            "beginning_stockholders_equity": row.get("beginning_stockholders_equity"),
            "ending_stockholders_equity": row.get("ending_stockholders_equity"),
            "avg_equity": row.get("avg_equity"),
            "roe": row.get("roe")
        })

    return {
        "symbol": symbol,
        "currency": get_currency(symbol, "USD"),
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }


def get_industry_quarterly_roe(symbol: str):
    """
    Retrieve historical industry-level Return on Equity (ROE) data
    for the industry to which a given stock symbol belongs.

    Args:
        symbol (str):
            Stock ticker symbol used to identify the corresponding industry,
            e.g., "TSLA", "AAPL" (case-insensitive).

    Returns:
        dict: {
            "symbol": str,
            "currency": str,                                        # Reporting currency (e.g., "USD")
            "period_type": "quarterly",                             # Industry ROE is reported on a quarterly basis
            "periods": list[str],                                   # List of fiscal period end dates
            "rows_returned": int,                                   # Number of periods returned
            "data": list[dict],                                     # List of records with:
                - period (str):                                     # Fiscal period end date
                - industry (str):                                   # Industry name
                - total_net_income_common_stockholders (decimal):   # Sum of net income attributable to common stockholders across all stocks in the industry
                - total_avg_equity (decimal):                       # For each stock, compute its average shareholders' equity as avg_equity(symbol), then calculate total_avg_equity = Σ avg_equity(symbol).
                - industry_roe (decimal):                           # Industry ROE = total_net_income_common_stockholders / total_avg_equity
        }
    """

    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.industry_roe()
    df['report_date'] = (
        pd.to_datetime(df['report_date'], errors='coerce')
        .dt.strftime('%Y-%m-%d')
    )

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "industry": row.get("industry"),
            "total_net_income_common_stockholders": row.get("total_net_income_common_stockholders"),
            "total_avg_equity": row.get("total_avg_equity"),
            "industry_roe": row.get("industry_roe")
        })

    return {
        "symbol": symbol,
        "currency": "USD",
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }