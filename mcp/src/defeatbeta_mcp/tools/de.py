from .util import create_ticker
from .util import get_currency


def get_stock_quarterly_debt_to_equity(symbol: str):
    """
    Retrieve historical Debt to Equity (D/E) Ratio data for a given stock symbol.

    The D/E ratio measures financial leverage by comparing total debt to
    stockholders' equity. A higher ratio indicates greater reliance on debt financing.

    Args:
        symbol (str):
            Stock ticker symbol, e.g., "TSLA", "AAPL" (case-insensitive).

    Returns:
        dict: {
            "symbol": str,
            "currency": str,                    # Reporting currency (e.g., "USD")
            "period_type": "quarterly",          # D/E Ratio is reported on a quarterly basis
            "periods": list[str],                # List of fiscal period end dates
            "rows_returned": int,                # Number of periods returned
            "data": list[dict],                  # List of records with:
                - period (str):                  # Fiscal period end date
                - total_debt (decimal):          # Total debt (short-term + long-term)
                - stockholders_equity (decimal): # Total stockholders' equity
                - debt_to_equity (decimal):      # D/E Ratio = total_debt / stockholders_equity
        }

    """

    symbol = symbol.upper()
    ticker = create_ticker(symbol)

    df = ticker.debt_to_equity()

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "total_debt": row.get("total_debt"),
            "stockholders_equity": row.get("stockholders_equity"),
            "debt_to_equity": row.get("debt_to_equity")
        })

    return {
        "symbol": symbol,
        "currency": get_currency(symbol, "USD"),
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }
