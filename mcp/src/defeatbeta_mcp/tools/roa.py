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