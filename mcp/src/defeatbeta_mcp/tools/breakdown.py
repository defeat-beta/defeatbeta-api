import pandas as pd
from .util import create_ticker

def get_quarterly_revenue_by_segment(symbol: str):
    """
    Retrieve quarterly revenue breakdown by business segment for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol (e.g. "TSLA", "AMD", "NVDA").

    Returns:
        dict: {
            "symbol": str,
            "period_type": "quarterly",
            "periods": list[str],     # e.g. ["2024-09-30", "2024-12-31", ...]
            "segments": list[str],    # e.g. ["Online Marketing Services", "Transaction Services"]
            "rows_returned": int,
            "data": [
                {
                    "period": str,
                    "revenue": {
                        "<segment>": float | None,
                        ...
                    },
                    "currency": "usd"
                },
                ...
            ]
        }
    """
    symbol = symbol.upper()
    ticker = create_ticker(symbol)

    df = ticker.revenue_by_segment()

    if df is None or df.empty:
        return {
            "symbol": symbol,
            "period_type": "quarterly",
            "periods": [],
            "segments": [],
            "rows_returned": 0,
            "data": []
        }

    df = df.copy()
    df["report_date"] = pd.to_datetime(df["report_date"])
    df = df.sort_values("report_date", ascending=True).reset_index(drop=True)

    segment_cols = sorted(c for c in df.columns if c != "report_date")

    data = []
    for _, row in df.iterrows():
        values = {}
        for seg in segment_cols:
            val = row.get(seg)
            if pd.isna(val):
                values[seg] = None
            else:
                try:
                    values[seg] = float(val)
                except Exception:
                    values[seg] = None

        data.append({
            "period": row["report_date"].strftime("%Y-%m-%d"),
            "revenue": values,
            "currency": "usd"
        })

    return {
        "symbol": symbol,
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "segments": segment_cols,
        "rows_returned": len(data),
        "data": data
    }

def get_quarterly_revenue_by_geography(symbol: str):
    """
    Retrieve quarterly revenue breakdown by geography for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol (e.g. "TSLA", "AMD", "NVDA").

    Returns:
        dict: {
            "symbol": str,
            "period_type": "quarterly",
            "periods": list[str],    # e.g. ["2024-09-30", "2024-12-31", ...]
            "regions": list[str],    # e.g. ["China", "United States", "Other"]
            "rows_returned": int,
            "data": [
                {
                    "period": str,
                    "revenue": {
                        "<region>": float | None,
                        ...
                    },
                    "currency": "usd"
                },
                ...
            ]
        }
    """
    symbol = symbol.upper()
    ticker = create_ticker(symbol)

    df = ticker.revenue_by_geography()

    if df is None or df.empty:
        return {
            "symbol": symbol,
            "period_type": "quarterly",
            "periods": [],
            "regions": [],
            "rows_returned": 0,
            "data": []
        }

    df = df.copy()
    df["report_date"] = pd.to_datetime(df["report_date"])
    df = df.sort_values("report_date", ascending=True).reset_index(drop=True)

    region_cols = sorted(c for c in df.columns if c != "report_date")

    data = []
    for _, row in df.iterrows():
        values = {}
        for region in region_cols:
            val = row.get(region)
            if pd.isna(val):
                values[region] = None
            else:
                try:
                    values[region] = float(val)
                except Exception:
                    values[region] = None

        data.append({
            "period": row["report_date"].strftime("%Y-%m-%d"),
            "revenue": values,
            "currency": "usd"
        })

    return {
        "symbol": symbol,
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "regions": region_cols,
        "rows_returned": len(data),
        "data": data
    }
