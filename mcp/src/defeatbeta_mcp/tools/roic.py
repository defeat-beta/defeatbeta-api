from .util import create_ticker
from .util import get_currency


def get_stock_quarterly_roic(symbol: str):
    """
        Retrieve historical Return on Invested Capital (ROIC) data for a given stock symbol.

        [!WARN]
        ROIC is generally NOT applicable to banks and other financial institutions,
        due to their fundamentally different balance sheet structures.

        Args:
            symbol (str):
                Stock ticker symbol, e.g., "TSLA", "AAPL" (case-insensitive).

        Returns:
            dict: {
                "symbol": str,
                "currency": str,                              # Reporting currency (e.g., "USD")
                "period_type": "quarterly",                   # ROIC is reported on a quarterly basis
                "periods": list[str],                         # List of fiscal period end dates
                "rows_returned": int,                         # Number of periods returned
                "data": list[dict],                           # List of records with:
                    - period (str):                           # Fiscal period end date
                    - ebit (decimal):                         # Earnings Before Interest and Taxes (operating income)
                    - tax_rate_for_calcs (decimal):           # Effective tax rate used for ROIC calculation
                    - nopat (decimal):                        # Net Operating Profit After Tax = ebit * (1 - tax_rate_for_calcs)
                    - beginning_invested_capital (decimal):   # Invested capital at the beginning of the quarter (i.e., invested capital from the prior quarter)
                    - ending_invested_capital (decimal):      # Invested capital at the end of the current quarter
                    - avg_invested_capital (decimal):         # Average invested capital = (beginning_invested_capital + ending_invested_capital) / 2
                    - roic (decimal):                         # Return on Invested Capital = nopat / avg_invested_capital
            }

    """

    symbol = symbol.upper()
    ticker = create_ticker(symbol)

    df = ticker.roic()

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "ebit": row.get("ebit"),
            "tax_rate_for_calcs": row.get("tax_rate_for_calcs"),
            "nopat": row.get("nopat"),
            "beginning_invested_capital": row.get("beginning_invested_capital"),
            "ending_invested_capital": row.get("ending_invested_capital"),
            "avg_invested_capital": row.get("avg_invested_capital"),
            "roic": row.get("roic")
        })

    return {
        "symbol": symbol,
        "currency": get_currency(symbol, "USD"),
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }