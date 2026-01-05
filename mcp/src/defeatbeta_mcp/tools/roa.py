from defeatbeta_api.data.ticker import Ticker
from .util import get_currency


def get_stock_quarterly_roa(symbol: str):
    """
    Retrieve historical Return on Assert (ROA) data for a given stock symbol.

    Args:
        symbol (str):
            Stock ticker symbol, e.g., "TSLA", "AAPL" (case-insensitive).

    Returns:
        dict: {
            "symbol": str,
            "currency": str,                                 # Reporting currency (e.g., "USD")
            "period_type": "quarterly",                      # ROA is reported on quarterly basis
            "periods": list[str],                            # List of fiscal period end dates
            "rows_returned": int,                            # Number of periods returned
            "data": list[dict],                              # List of records with:
                - period (str):                              # Fiscal period end date
                - net_income_common_stockholders (decimal):  # Net income attributable to common stockholders
                - beginning_total_assets (decimal):          # Total assets at the beginning of the quarter (i.e., total assets from the prior quarter).
                - ending_total_assets (decimal):             # Total assets at the end of the current quarter.
                - avg_assets (decimal):                      # Average total assets = (beginning_total_assets + ending_total_assets) / 2
                - roa (decimal):                             # Return on Assert = net_income_common_stockholders / avg_assets
        }

    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.roa()

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "net_income_common_stockholders": row.get("net_income_common_stockholders"),
            "beginning_total_assets": row.get("beginning_total_assets"),
            "ending_total_assets": row.get("ending_total_assets"),
            "avg_assets": row.get("avg_assets"),
            "roa": row.get("roa")
        })

    return {
        "symbol": symbol,
        "currency": get_currency(symbol, "USD"),
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }


def get_industry_quarterly_roa(symbol: str):
    """
    Retrieve historical industry-level Return on Assets (ROA) data
    for the industry corresponding to a given stock symbol.

    Args:
        symbol (str):
            Stock ticker symbol used to identify the industry
            (e.g., "TSLA", "AAPL"). Case-insensitive.

    Returns:
        dict: {
            "symbol": str,                                          # Input stock symbol
            "currency": str,                                        # Reporting currency (e.g., "USD")
            "period_type": "quarterly",                             # Industry ROA is reported quarterly
            "periods": list[str],                                   # List of fiscal period end dates
            "rows_returned": int,                                   # Number of periods returned
            "data": list[dict],                                     # List of records with:
                - period (str):                                     # Fiscal period end date
                - industry (str):                                   # Industry name
                - total_net_income_common_stockholders (decimal):   # Sum of net income attributable to common stockholders across all stocks in the industry
                - total_avg_asserts (decimal):                      # For each stock, compute its average assets as avg_asserts(symbol), then calculate total_avg_asserts = Σ avg_asserts(symbol).
                - industry_roa (decimal):                           # Industry Return on Assets
        }
    """

    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.industry_roa()

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "industry": row.get("industry"),
            "total_net_income_common_stockholders": row.get("total_net_income_common_stockholders"),
            "total_avg_asserts": row.get("total_avg_asserts"),
            "industry_roa": row.get("industry_roa")
        })

    return {
        "symbol": symbol,
        "currency": get_currency(symbol, "USD"),
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }