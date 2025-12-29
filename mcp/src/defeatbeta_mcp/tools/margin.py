from defeatbeta_api.data.ticker import Ticker


def get_stock_quarterly_gross_margin(symbol: str):
    """
    Retrieve quarterly gross margin data for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol (e.g. "TSLA", "AMD", "NVDA").

    Returns:
        dict: {
            "symbol": str,
            "period_type": "quarterly",
            "periods": list[str],        # report dates (oldest -> newest)
            "rows_returned": int,
            "data": [
                {
                    "period": str,
                    "gross_profit": float | None,
                    "total_revenue": float | None,
                    "gross_margin": float | None
                },
                ...
            ]
        }
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.quarterly_gross_margin()

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "gross_profit": row.get("gross_profit"),
            "total_revenue": row.get("total_revenue"),
            "gross_margin": row.get("gross_margin")
        })

    return {
        "symbol": symbol,
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }

def get_stock_annual_gross_margin(symbol: str):
    """
    Retrieve annual gross margin data for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol (e.g. "TSLA", "AMD", "NVDA").

    Returns:
        dict: {
            "symbol": str,
            "period_type": "annual",
            "periods": list[str],        # report dates (oldest -> newest)
            "rows_returned": int,
            "data": [
                {
                    "period": str,
                    "gross_profit": float | None,
                    "total_revenue": float | None,
                    "gross_margin": float | None
                },
                ...
            ]
        }
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.annual_gross_margin()

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "gross_profit": row.get("gross_profit"),
            "total_revenue": row.get("total_revenue"),
            "gross_margin": row.get("gross_margin")
        })

    return {
        "symbol": symbol,
        "period_type": "annual",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }
