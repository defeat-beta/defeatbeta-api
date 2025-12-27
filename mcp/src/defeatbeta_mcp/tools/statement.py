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
            "periods": list[str],        # e.g. ["2024-12-31", "2024-09-30", ...]
            "rows_returned": int,          # number of periods
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
            "period_type": "quarterly",
            "periods": [],
            "rows_returned": 0,
            "statement": []
        }

    result = _build_statement(df, period_type="quarterly")
    result["symbol"] = symbol
    return result

def get_stock_annual_income_statement(symbol: str):
    """
    Retrieve the annual income statement for a given stock symbol.

    This tool returns income statement data structured by year, with
    each year represented as a record containing standardized income
    statement line items.

    Returns:
        dict: {
            "symbol": str,
            "period_type": "annual",
            "periods": list[str],        # e.g. ["2024-12-31", "2023-12-31", ...]
            "rows_returned": int,          # number of periods
            "statement": [
                {
                    "period": str,         # year-end date
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

    df = ticker.annual_income_statement().df()

    if df is None or df.empty:
        return {
            "symbol": symbol,
            "period_type": "annual",
            "periods": [],
            "rows_returned": 0,
            "statement": []
        }

    result = _build_statement(df, period_type="annual")
    result["symbol"] = symbol
    return result

def get_stock_quarterly_balance_sheet(symbol: str):
    """
    Retrieve the quarterly balance sheet for a given stock symbol.

    This tool returns balance sheet data structured by quarter, with
    each quarter represented as a record containing standardized balance
    sheet line items.

    Returns:
        dict: {
            "symbol": str,
            "period_type": "quarterly",
            "periods": list[str],        # e.g. ["2024-12-31", "2024-09-30", ...]
            "rows_returned": int,          # number of periods
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

    df = ticker.quarterly_balance_sheet().df()

    if df is None or df.empty:
        return {
            "symbol": symbol,
            "period_type": "quarterly",
            "periods": [],
            "rows_returned": 0,
            "statement": []
        }

    result = _build_statement(df, period_type="quarterly")
    result["symbol"] = symbol
    return result

def get_stock_annual_balance_sheet(symbol: str):
    """
    Retrieve the annual balance sheet for a given stock symbol.

    This tool returns balance sheet data structured by year, with
    each year represented as a record containing standardized balance
    sheet line items.

    Returns:
        dict: {
            "symbol": str,
            "period_type": "annual",
            "periods": list[str],        # e.g. ["2024-12-31", "2023-12-31", ...]
            "rows_returned": int,          # number of periods
            "statement": [
                {
                    "period": str,         # year-end date
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

    df = ticker.annual_balance_sheet().df()

    if df is None or df.empty:
        return {
            "symbol": symbol,
            "period_type": "annual",
            "periods": [],
            "rows_returned": 0,
            "statement": []
        }

    result = _build_statement(df, period_type="annual")
    result["symbol"] = symbol
    return result

def _build_statement(df: pd.DataFrame, period_type: str):
    breakdown_col = "Breakdown"

    period_cols = [
        c for c in df.columns
        if c != breakdown_col and c.upper() != "TTM"
    ]

    statement = []

    for period in period_cols:
        items = {}
        for _, row in df.iterrows():
            key = row[breakdown_col]
            items[key] = _normalize_value(row[period])

        statement.append({
            "period": period,
            "items": items
        })

    return {
        "period_type": period_type,
        "periods": period_cols,
        "rows_returned": len(statement),
        "statement": statement
    }

def _normalize_value(v):
    if pd.isna(v):
        return None
    if isinstance(v, str):
        v = v.replace(",", "").strip()
        if v in ("", "*"):
            return None
    try:
        return float(v)
    except Exception:
        return None