import pandas as pd
from defeatbeta_api.data.ticker import Ticker

def get_stock_quarterly_income_statement(symbol: str):
    """
    Retrieve the quarterly income statement for a given stock symbol.

    This tool returns income statement data structured by quarter, with
    each quarter represented as a record containing standardized income
    statement line items.

    Returns:
        dict: {
            "symbol": str,
            "period_type": "quarterly",
            "quarters": list[str],        # e.g. ["2024-12-31", "2024-09-30", ...]
            "rows_returned": int,          # number of quarters
            "statement": [
                {
                    "period": str,         # quarter end date
                    "items": {
                        "<breakdown_name>": float | None,
                        ...
                    }
                },
                ...
            ]
        }
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.quarterly_income_statement().df()

    if df is None or df.empty:
        return {
            "symbol": symbol,
            "rows_returned": 0,
            "statement": []
        }

    # First column is Breakdown, others are TTM / quarter end dates
    breakdown_col = "Breakdown"
    period_cols = [c for c in df.columns if c != breakdown_col]

    # Clean values: "*" -> None, numbers -> float
    def normalize_value(v):
        if pd.isna(v):
            return None
        if isinstance(v, str):
            v = v.replace(",", "").strip()
            if v == "*" or v == "":
                return None
        try:
            return float(v)
        except Exception:
            return None

    statement = []

    for period in period_cols:
        items = {}
        for _, row in df.iterrows():
            key = row[breakdown_col]
            value = normalize_value(row[period])
            items[key] = value

        statement.append({
            "period": period,
            "items": items
        })

    return {
        "symbol": symbol,
        "period_type": "quarterly",
        "quarters": period_cols,
        "rows_returned": len(statement),
        "statement": statement
    }
