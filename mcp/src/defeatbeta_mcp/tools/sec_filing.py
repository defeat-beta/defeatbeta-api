import pandas as pd

from .util import create_ticker


def get_stock_sec_filings(symbol: str, start_date: str = None, end_date: str = None):
    """
    Retrieve SEC (U.S. Securities and Exchange Commission) filing records
    for a given publicly traded company.

    This tool returns a list of SEC filings, including annual reports (10-K),
    quarterly reports (10-Q), current reports (8-K), insider trading forms,
    and institutional holdings reports.

    Args:
        symbol (str): Stock ticker symbol (e.g., "TSLA", "AAPL").
                      Case-insensitive and will be converted to uppercase.
        start_date: Optional start date in YYYY-MM-DD format (e.g., "2020-01-01").
                    If None, data starts from the earliest available date.
        end_date: Optional end date in YYYY-MM-DD format (e.g., "2024-12-31").
                  If None, data goes up to the most recent filing.

    Returns:
        dict: A dictionary with the following structure:
            {
                "symbol": "TSLA",
                "date_range": "2010-02-01 to 2024-12-31",
                "rows_returned": 500,
                "truncated": false,
                "filings": [
                    {
                        "form_type": "10-K",
                        "filing_date": "2024-01-29",
                        "report_date": "2023-12-31",
                        "acceptance_date_time": "2024-01-29T16:05:02.000Z",
                        "cik": "0001318605",
                        "accession_number": "0001628280-24-002390",
                        "company_name": "Tesla, Inc.",
                        "filing_url": "https://www.sec.gov/Archives/edgar/data/..."
                    },
                    ...
                ]
            }

    Supported Form Types:
        - US Domestic Companies:
            - 10-K, 10-K/A: Annual report
            - 10-Q, 10-Q/A: Quarterly report
            - 8-K, 8-K/A: Current report (material events)
            - DEF 14A, DEFA14A: Proxy statement
        - Insider Trading:
            - 3, 3/A: Initial beneficial ownership
            - 4, 4/A: Changes in beneficial ownership
            - 5, 5/A: Annual beneficial ownership
            - 144, 144/A: Notice of proposed sale
        - Institutional Holdings:
            - 13F-HR, 13F-HR/A: Institutional holdings (quarterly)
            - SC 13G, SC 13G/A: Passive investor holdings (>5%)
            - SC 13D, SC 13D/A: Active investor holdings (>5%)
        - Foreign Private Issuers (e.g., BABA, PDD):
            - 20-F, 20-F/A: Annual report
            - 6-K, 6-K/A: Current report
        - Canadian Companies (e.g., SHOP, TD):
            - 40-F, 40-F/A: Annual report
        - ETFs/Investment Companies (e.g., SPY, QQQ):
            - N-CSR, N-CSRS: Shareholder reports
            - NPORT-P: Monthly portfolio holdings

    Important note on data limits:
        To prevent responses from becoming too large for the language model to process
        (which can cause errors or token limit exceeded issues), this tool caps the
        maximum number of rows returned at 500 (MAX_ROWS = 500).
        When the requested range contains more than 500 rows, only the most recent
        500 filings are returned, and "truncated": true is set.

        If you need data further back:
        - Make multiple calls with different (earlier) date ranges
        - Or call with a narrower start_date/end_date to stay under the limit

    Notes:
        - Filings are returned in chronological order (oldest first).
        - For insider trading analysis, look for form type "4" to see stock transactions.
        - For annual financials, look for "10-K" (US) or "20-F" (foreign).
        - If no filings are found, an empty list is returned.
    """
    symbol = symbol.upper()
    ticker = create_ticker(symbol)
    df = ticker.sec_filing()

    if df.empty:
        return {
            "symbol": symbol,
            "rows_returned": 0,
            "truncated": False,
            "filings": []
        }

    # Convert filing_date to datetime for filtering and sorting
    df["filing_date"] = pd.to_datetime(df["filing_date"])

    # Sort by filing_date ascending (oldest first)
    df = df.sort_values("filing_date", ascending=True).reset_index(drop=True)

    # Apply date filters
    if start_date:
        try:
            start_dt = pd.to_datetime(start_date)
            df = df[df["filing_date"] >= start_dt]
        except ValueError:
            return {"error": f"Invalid start_date format: '{start_date}'. Use YYYY-MM-DD."}

    if end_date:
        try:
            end_dt = pd.to_datetime(end_date)
            df = df[df["filing_date"] <= end_dt]
        except ValueError:
            return {"error": f"Invalid end_date format: '{end_date}'. Use YYYY-MM-DD."}

    if df.empty:
        return {
            "symbol": symbol,
            "message": "No filings found for the specified date range."
        }

    # Safety cap to avoid token overflow in LLM context
    MAX_ROWS = 500
    if len(df) > MAX_ROWS:
        df = df.tail(MAX_ROWS)  # Keep the newest filings
        truncated = True
    else:
        truncated = False

    # Select and normalize fields for LLM-friendly JSON output
    columns = [
        "form_type",
        "filing_date",
        "report_date",
        "acceptance_date_time",
        "cik",
        "accession_number",
        "company_name",
        "filing_url"
    ]

    # Only include columns that exist in the dataframe
    available_columns = [col for col in columns if col in df.columns]
    filings_df = df[available_columns].copy()

    # Convert date columns to string format
    if "filing_date" in filings_df.columns:
        filings_df["filing_date"] = filings_df["filing_date"].dt.strftime("%Y-%m-%d")
    if "report_date" in filings_df.columns:
        filings_df["report_date"] = filings_df["report_date"].astype(str)

    # Convert pandas NA to None for clean JSON serialization
    filings_df = filings_df.where(filings_df.notna(), None)

    return {
        "symbol": symbol,
        "date_range": f"{df['filing_date'].min().date()} to {df['filing_date'].max().date()}",
        "rows_returned": len(filings_df),
        "truncated": truncated,
        "filings": filings_df.to_dict(orient="records")
    }
