from .util import create_ticker

# Maps period_type filter values to the SEC form types they correspond to.
# Domestic companies:  10-K / 10-K/A = annual;  10-Q / 10-Q/A = quarterly
# Foreign private issuers (ADRs etc.): 20-F / 20-F/A = annual;  6-K / 6-K/A = interim (quarterly/semi-annual)
_ANNUAL_FORM_TYPES = {"10-K", "10-K/A", "20-F", "20-F/A"}
_QUARTERLY_FORM_TYPES = {"10-Q", "10-Q/A", "6-K", "6-K/A"}


def get_revenue_breakdown(symbol: str, period_type: str = None):
    """
    Retrieve all revenue breakdown data for a given stock symbol, as reported in SEC filings.

    Unlike fixed segment/geography splits, this returns every breakdown table available
    in the filing (e.g. by segment, by geography, by product line, by service type, etc.).
    The breakdown_type field identifies which table each row belongs to.

    Args:
        symbol (str): Stock ticker symbol (e.g. "TSLA", "AMD", "NVDA").
        period_type (str): Optional filter — "annual" or "quarterly".
                           Filtered by form_type: "annual" keeps 10-K/10-K/A rows,
                           "quarterly" keeps 10-Q/10-Q/A rows.
                           If omitted, all rows are returned.

    Returns:
        dict: {
            "symbol": str,
            "rows_returned": int,
            "breakdown_types": list[str],   # distinct table names present in the data
            "data": list[dict]              # each record contains:
                - report_date (str):        # period end date, e.g. "2024-12-31"
                - period_label (str):       # the data period this report covers, formatted as
                                            # "start~end" (e.g. "2024-01-01~2024-12-31") or
                                            # just "end" when no start date is available
                - form_type (str):          # SEC form type, e.g. "10-K", "10-Q", "10-K/A"
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

    if period_type == "annual":
        df = df[df["form_type"].isin(_ANNUAL_FORM_TYPES)]
    elif period_type == "quarterly":
        df = df[df["form_type"].isin(_QUARTERLY_FORM_TYPES)]

    breakdown_types = sorted(df["breakdown_type"].dropna().unique().tolist())

    records = []
    for _, row in df.iterrows():
        val = row.get("item_value")
        parent = row.get("parent_name")
        raw_label = row.get("period_label")
        # period_label from XBRL: "2024-01-01/2024-12-31" (start~end) or "2024-12-31" (end only)
        period_label = str(raw_label).replace("/", "~") if raw_label else None
        records.append({
            "report_date": str(row["report_date"]),
            "period_label": period_label,
            "form_type": str(row["form_type"]) if row.get("form_type") else None,
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
