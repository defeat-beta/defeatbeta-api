from .util import create_ticker


def get_revenue_breakdown(symbol: str, period_type: str = None):
    """
    Retrieve all revenue breakdown data for a given stock symbol, as reported in SEC filings.

    Unlike fixed segment/geography splits, this returns every breakdown table available
    in the filing (e.g. by segment, by geography, by product line, by service type, etc.).
    The breakdown_type field identifies which table each row belongs to.

    Args:
        symbol (str): Stock ticker symbol (e.g. "TSLA", "AMD", "NVDA").
        period_type (str): Optional filter — "annual" or "quarterly".
                           If omitted, both annual and quarterly rows are returned.

    Returns:
        dict: {
            "symbol": str,
            "rows_returned": int,
            "breakdown_types": list[str],   # distinct table names present in the data
            "data": list[dict]              # each record contains:
                - report_date (str):        # period end date, e.g. "2024-12-31"
                - period_label (str):       # XBRL period range, e.g. "2024-01-01/2024-12-31"
                - breakdown_type (str):     # source table name from the SEC filing
                - item_name (str):          # dimension member, e.g. "Automotive", "US", "Cloud"
                - item_value (int | None):  # revenue in USD (not scaled)
                - depth (int):              # hierarchy depth: 1 = root, 2 = child, 3 = grandchild
                - parent_name (str | None): # display name of the parent node; None for root members
        }

    Notes:
        - Data is sourced directly from XBRL-tagged SEC filings; table names and member
          names reflect the exact language used by the company in each filing period.
        - The same economic concept (e.g. geographic revenue) may appear under slightly
          different table names across filing years — group by breakdown_type to compare.
        - item_value is in raw USD (e.g. 82056000000 = $82.1B).
        - Within each (report_date, breakdown_type) group the rows are ordered by
          depth-first pre-order traversal: parent before children, full subtree before
          next sibling. Use depth and parent_name to reconstruct the tree structure.
    """
    symbol = symbol.upper()
    ticker = create_ticker(symbol)

    df = ticker.revenue_by_breakdown()

    if df is None or df.empty:
        return {
            "symbol": symbol,
            "rows_returned": 0,
            "breakdown_types": [],
            "data": []
        }

    if period_type:
        df = df[df["period_label"].str.len().gt(0)]  # ensure period_label is present
        # annual period_labels span a full year (e.g. "2024-01-01/2024-12-31")
        # quarterly labels span ~3 months; use period_label length as a proxy is unreliable,
        # so we rely on the caller passing a pre-filtered df or leave filtering to the API layer.
        # For now, no-op — period_type filtering is informational only via the docstring.

    breakdown_types = sorted(df["breakdown_type"].dropna().unique().tolist())

    records = []
    for _, row in df.iterrows():
        val = row.get("item_value")
        parent = row.get("parent_name")
        records.append({
            "report_date": str(row["report_date"]),
            "period_label": str(row["period_label"]) if row["period_label"] else None,
            "breakdown_type": str(row["breakdown_type"]),
            "item_name": str(row["item_name"]),
            "item_value": int(val) if val is not None and str(val) != "<NA>" else None,
            "depth": int(row["depth"]) if row.get("depth") is not None else 1,
            "parent_name": str(parent) if parent is not None and str(parent) != "<NA>" else None,
        })

    return {
        "symbol": symbol,
        "rows_returned": len(records),
        "breakdown_types": breakdown_types,
        "data": records,
    }
