import pandas as pd
from defeatbeta_api.data.ticker import Ticker

def get_quarterly_revenue_by_segment(symbol: str):
    """
    Retrieve quarterly revenue broken down by business segment for
    a given stock symbol.

    This tool returns segment-level revenue data by reporting period.

    Args:
        symbol (str): Stock ticker symbol (e.g. "TSLA", "AMD", "NVDA").

    Returns:
        dict: {
            "symbol": str,
            "period_type": "quarterly",
            "periods": list[str],          # report dates
            "rows_returned": int,
            "segments": list[str],         # segment names
            "statement": [
                {
                    "period": str,         # report_date
                    "items": {
                        "<segment_name>": float | None,
                        ...
                    }
                },
                ...
            ]
        }
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.revenue_by_segment()

    if df is None or df.empty:
        return {
            "symbol": symbol,
            "period_type": "quarterly",
            "periods": [],
            "rows_returned": 0,
            "segments": [],
            "statement": []
        }

    # Ensure report_date is string
    df = df.copy()
    df["report_date"] = df["report_date"].astype(str)

    period_col = "report_date"
    segment_cols = [c for c in df.columns if c != period_col]

    def normalize_value(v):
        if pd.isna(v):
            return None
        try:
            return float(v)
        except Exception:
            return None

    statement = []
    for _, row in df.iterrows():
        items = {}
        for seg in segment_cols:
            items[seg] = normalize_value(row[seg])

        statement.append({
            "period": row[period_col],
            "items": items
        })

    return {
        "symbol": symbol,
        "period_type": "quarterly",
        "periods": df[period_col].tolist(),
        "rows_returned": len(statement),
        "segments": segment_cols,
        "statement": statement
    }
