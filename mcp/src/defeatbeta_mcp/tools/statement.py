import pandas as pd
from .util import create_ticker, get_currency


_RENDERING_GUIDE = """
    Rendering guide for `statement` rows:
        - periods: ordered list of period end dates; values[i] corresponds to periods[i]
        - label: the display name of this line item (already cleaned, no prefix characters)
        - indent: hierarchy depth (0 = top-level, 1 = sub-item, 2 = sub-sub-item, ...).
                  When rendering, prefix each label with (indent * 2) spaces for alignment.
        - is_section: if True, this row is a section header that groups the rows below it
                      (i.e. the rows immediately following with indent = this.indent + 1 are its children).
                      Render section headers in bold or with emphasis.
        - values: list of raw numbers (float | None) aligned to `periods`.
                  None means the data is not available for that period.
                  Numbers are in the same unit as `currency` (e.g. USD thousands).

    Example rendering of two rows:
        indent=0, is_section=True,  label="Gross Profit"   → **Gross Profit**     10,000  9,500  8,800
        indent=1, is_section=False, label="Cost of Revenue" →   Cost of Revenue    4,000  4,200  3,900
"""

_EMPTY_STATEMENT = {
    "periods": [],
    "statement": []
}


def get_stock_quarterly_income_statement(symbol: str):
    """
    Retrieve the quarterly income statement for a given stock symbol.

    Returns:
        dict: {
            "currency": str,             # e.g. "USD"
            "period_type": "quarterly",
            "periods": list[str],        # e.g. ["2024-12-31", "2024-09-30", ...]
            "statement": [
                {
                    "label": str,        # line item name
                    "indent": int,       # hierarchy depth: 0 = top-level, 1 = sub-item, ...
                    "is_section": bool,  # True if this row is a section header with children below
                    "values": list[float | None]  # raw numbers aligned to `periods`
                },
                ...
            ]
        }

    Rendering guide:
        - Prefix each label with (indent * 2) spaces for visual hierarchy.
        - Render rows where is_section=True in bold; they group the rows immediately below
          them (those with indent = this.indent + 1).
        - values[i] corresponds to periods[i]; None means data not available.
        - Numbers are in the stated currency unit (e.g. USD thousands).
    """
    symbol = symbol.upper()
    ticker = create_ticker(symbol)
    currency = get_currency(symbol)

    stmt = ticker.quarterly_income_statement()
    df = stmt.df()

    if df is None or df.empty:
        return {"currency": currency, "period_type": "quarterly", **_EMPTY_STATEMENT}

    return _build_statement(df, stmt.row_meta, currency, period_type="quarterly")


def get_stock_annual_income_statement(symbol: str):

    """
    Retrieve the annual income statement for a given stock symbol.

    Returns:
        dict: {
            "currency": str,             # e.g. "USD"
            "period_type": "annual",
            "periods": list[str],        # e.g. ["2024-12-31", "2023-12-31", ...]
            "statement": [
                {
                    "label": str,        # line item name
                    "indent": int,       # hierarchy depth: 0 = top-level, 1 = sub-item, ...
                    "is_section": bool,  # True if this row is a section header with children below
                    "values": list[float | None]  # raw numbers aligned to `periods`
                },
                ...
            ]
        }

    Rendering guide:
        - Prefix each label with (indent * 2) spaces for visual hierarchy.
        - Render rows where is_section=True in bold; they group the rows immediately below
          them (those with indent = this.indent + 1).
        - values[i] corresponds to periods[i]; None means data not available.
        - Numbers are in the stated currency unit (e.g. USD thousands).
    """
    symbol = symbol.upper()
    ticker = create_ticker(symbol)
    currency = get_currency(symbol)

    stmt = ticker.annual_income_statement()
    df = stmt.df()

    if df is None or df.empty:
        return {"currency": currency, "period_type": "annual", **_EMPTY_STATEMENT}

    return _build_statement(df, stmt.row_meta, currency, period_type="annual")


def get_stock_quarterly_balance_sheet(symbol: str):
    """
    Retrieve the quarterly balance sheet for a given stock symbol.

    Returns:
        dict: {
            "currency": str,             # e.g. "USD"
            "period_type": "quarterly",
            "periods": list[str],        # e.g. ["2024-12-31", "2024-09-30", ...]
            "statement": [
                {
                    "label": str,        # line item name
                    "indent": int,       # hierarchy depth: 0 = top-level, 1 = sub-item, ...
                    "is_section": bool,  # True if this row is a section header with children below
                    "values": list[float | None]  # raw numbers aligned to `periods`
                },
                ...
            ]
        }

    Rendering guide:
        - Prefix each label with (indent * 2) spaces for visual hierarchy.
        - Render rows where is_section=True in bold; they group the rows immediately below
          them (those with indent = this.indent + 1).
        - values[i] corresponds to periods[i]; None means data not available.
        - Numbers are in the stated currency unit (e.g. USD thousands).
    """
    symbol = symbol.upper()
    ticker = create_ticker(symbol)
    currency = get_currency(symbol)

    stmt = ticker.quarterly_balance_sheet()
    df = stmt.df()

    if df is None or df.empty:
        return {"currency": currency, "period_type": "quarterly", **_EMPTY_STATEMENT}

    return _build_statement(df, stmt.row_meta, currency, period_type="quarterly")


def get_stock_annual_balance_sheet(symbol: str):
    """
    Retrieve the annual balance sheet for a given stock symbol.

    Returns:
        dict: {
            "currency": str,             # e.g. "USD"
            "period_type": "annual",
            "periods": list[str],        # e.g. ["2024-12-31", "2023-12-31", ...]
            "statement": [
                {
                    "label": str,        # line item name
                    "indent": int,       # hierarchy depth: 0 = top-level, 1 = sub-item, ...
                    "is_section": bool,  # True if this row is a section header with children below
                    "values": list[float | None]  # raw numbers aligned to `periods`
                },
                ...
            ]
        }

    Rendering guide:
        - Prefix each label with (indent * 2) spaces for visual hierarchy.
        - Render rows where is_section=True in bold; they group the rows immediately below
          them (those with indent = this.indent + 1).
        - values[i] corresponds to periods[i]; None means data not available.
        - Numbers are in the stated currency unit (e.g. USD thousands).
    """
    symbol = symbol.upper()
    ticker = create_ticker(symbol)
    currency = get_currency(symbol)

    stmt = ticker.annual_balance_sheet()
    df = stmt.df()

    if df is None or df.empty:
        return {"currency": currency, "period_type": "annual", **_EMPTY_STATEMENT}

    return _build_statement(df, stmt.row_meta, currency, period_type="annual")


def get_stock_quarterly_cash_flow(symbol: str):
    """
    Retrieve the quarterly cash flow statement for a given stock symbol.

    Returns:
        dict: {
            "currency": str,             # e.g. "USD"
            "period_type": "quarterly",
            "periods": list[str],        # e.g. ["2024-12-31", "2024-09-30", ...]
            "statement": [
                {
                    "label": str,        # line item name
                    "indent": int,       # hierarchy depth: 0 = top-level, 1 = sub-item, ...
                    "is_section": bool,  # True if this row is a section header with children below
                    "values": list[float | None]  # raw numbers aligned to `periods`
                },
                ...
            ]
        }

    Rendering guide:
        - Prefix each label with (indent * 2) spaces for visual hierarchy.
        - Render rows where is_section=True in bold; they group the rows immediately below
          them (those with indent = this.indent + 1).
        - values[i] corresponds to periods[i]; None means data not available.
        - Numbers are in the stated currency unit (e.g. USD thousands).
    """
    symbol = symbol.upper()
    ticker = create_ticker(symbol)
    currency = get_currency(symbol)

    stmt = ticker.quarterly_cash_flow()
    df = stmt.df()

    if df is None or df.empty:
        return {"currency": currency, "period_type": "quarterly", **_EMPTY_STATEMENT}

    return _build_statement(df, stmt.row_meta, currency, period_type="quarterly")


def get_stock_annual_cash_flow(symbol: str):
    """
    Retrieve the annual cash flow statement for a given stock symbol.

    Returns:
        dict: {
            "currency": str,             # e.g. "USD"
            "period_type": "annual",
            "periods": list[str],        # e.g. ["2024-12-31", "2023-12-31", ...]
            "statement": [
                {
                    "label": str,        # line item name
                    "indent": int,       # hierarchy depth: 0 = top-level, 1 = sub-item, ...
                    "is_section": bool,  # True if this row is a section header with children below
                    "values": list[float | None]  # raw numbers aligned to `periods`
                },
                ...
            ]
        }

    Rendering guide:
        - Prefix each label with (indent * 2) spaces for visual hierarchy.
        - Render rows where is_section=True in bold; they group the rows immediately below
          them (those with indent = this.indent + 1).
        - values[i] corresponds to periods[i]; None means data not available.
        - Numbers are in the stated currency unit (e.g. USD thousands).
    """
    symbol = symbol.upper()
    ticker = create_ticker(symbol)
    currency = get_currency(symbol)

    stmt = ticker.annual_cash_flow()
    df = stmt.df()

    if df is None or df.empty:
        return {"currency": currency, "period_type": "annual", **_EMPTY_STATEMENT}

    return _build_statement(df, stmt.row_meta, currency, period_type="annual")


def _build_statement(df: pd.DataFrame, row_meta: list, currency: str, period_type: str) -> dict:
    breakdown_col = "Breakdown"

    period_cols = [
        c for c in df.columns
        if c != breakdown_col and c.upper() != "TTM"
    ]

    statement = []
    for i, (_, row) in enumerate(df.iterrows()):
        meta = row_meta[i] if i < len(row_meta) else {"indent": 0, "is_section": False}
        values = [_normalize_value(row[p]) for p in period_cols]
        statement.append({
            "label": str(row[breakdown_col]),
            "indent": meta["indent"],
            "is_section": meta["is_section"],
            "values": values,
        })

    return {
        "currency": currency,
        "period_type": period_type,
        "periods": period_cols,
        "statement": statement,
    }


def _normalize_value(v) -> float | None:
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
