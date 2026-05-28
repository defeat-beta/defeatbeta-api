from .util import create_ticker

_VALID_PERIOD_TYPES = {"quarterly", "trailing"}


def _is_missing(value):
    return value is None or str(value) in ("<NA>", "nan", "NaT")


def _optional_str(value):
    if _is_missing(value):
        return None
    return str(value)


def _optional_int(value):
    if _is_missing(value):
        return None
    return int(value)


def get_revenue_breakdown(symbol: str, period_type: str):
    """
    Retrieve revenue / KPI breakdown disclosures for a given stock symbol.

    Each company discloses one or more breakdowns of its revenue (or other key
    metrics) — for example by segment, geography, product line, customer type,
    or deal size. This tool returns every disclosed breakdown table in long
    format; group by `breakdown` to separate them.

    Args:
        symbol (str): Stock ticker symbol (e.g. "PLTR", "AMD", "TSLA").
        period_type (str): Required. One of:
            - "quarterly":  values for a single fiscal quarter
            - "trailing":   values for the trailing twelve months ending on report_date

    Returns:
        dict: {
            "symbol": str,
            "period_type": str,
            "rows_returned": int,
            "breakdowns": list[dict],   # one entry per distinct breakdown table:
                - "breakdown" (str):         slug, e.g. "revenue-by-segment"
                - "breakdown_name" (str):    display name, e.g. "Revenue by Segment"
                - "value_type" (str):        "CURRENCY", "NUMBER", etc.
                - "currency" (str | None):   ISO currency code if value_type=CURRENCY, else None
            "data": list[dict]          # each record:
                - "breakdown" (str):         which breakdown this row belongs to
                - "report_date" (str):       period end date, "YYYY-MM-DD"
                - "series_name" (str):       dimension member, e.g. "Government", "US", "Data Center"
                - "value" (int | None):      numeric value for (report_date, series_name)
        }

    Notes:
        - To form a wide table for one breakdown, group `data` by `breakdown`,
          then pivot rows on `series_name` with `report_date` as the index.
        - `value` is raw — for CURRENCY breakdowns it is in the unit of `currency`
          (typically USD); for NUMBER breakdowns it is the raw count.
    """
    symbol = symbol.upper()

    if period_type not in _VALID_PERIOD_TYPES:
        raise ValueError(
            f"Invalid period_type: {period_type!r}. "
            f"Must be one of {sorted(_VALID_PERIOD_TYPES)}."
        )

    ticker = create_ticker(symbol)

    if period_type == "quarterly":
        df = ticker.quarterly_revenue_by_breakdown()
    else:
        df = ticker.trailing_revenue_by_breakdown()

    if df is None or df.empty:
        return {
            "symbol": symbol,
            "period_type": period_type,
            "rows_returned": 0,
            "breakdowns": [],
            "data": [],
        }

    meta_df = (
        df[["breakdown", "breakdown_name", "value_type", "currency"]]
        .drop_duplicates(subset=["breakdown"])
        .sort_values("breakdown")
    )
    breakdowns = []
    for _, row in meta_df.iterrows():
        breakdowns.append({
            "breakdown": str(row["breakdown"]),
            "breakdown_name": _optional_str(row.get("breakdown_name")),
            "value_type": _optional_str(row.get("value_type")),
            "currency": _optional_str(row.get("currency")),
        })

    records = []
    for _, row in df.iterrows():
        records.append({
            "breakdown": str(row["breakdown"]),
            "report_date": str(row["report_date"]),
            "series_name": str(row["series_name"]),
            "value": _optional_int(row.get("value")),
        })

    return {
        "symbol": symbol,
        "period_type": period_type,
        "rows_returned": len(records),
        "breakdowns": breakdowns,
        "data": records,
    }
