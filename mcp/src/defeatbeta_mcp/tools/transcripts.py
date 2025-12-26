from defeatbeta_api.data.ticker import Ticker

def get_stock_earning_call_transcripts_list(symbol: str):
    """
    Retrieve a list of available earnings call transcripts for a company.

    This tool returns metadata for all available earnings call transcripts,
    including fiscal year, fiscal quarter, and report date.
    It does NOT return the full transcript content.

    Use this tool to:
      - Discover which earnings calls are available
      - Identify the most recent fiscal quarter
      - Select a specific period for detailed transcript retrieval

    Args:
        symbol (str): Stock ticker symbol (e.g., "TSLA", "AAPL").
                      Case-insensitive and will be converted to uppercase.

    Returns:
        dict: A dictionary with the following structure:
            {
                "symbol": "TSLA",
                "rows_returned": 25,
                "transcripts": [
                    {
                        "fiscal_year": 2024,
                        "fiscal_quarter": 4,
                        "report_date": "2025-01-29"
                    },
                    ...
                ]
            }

    Notes:
        - This tool provides metadata only.
        - Use `get_earning_call_transcript` to retrieve the full transcript
          for a specific fiscal year and quarter.
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    transcripts = ticker.earning_call_transcripts()
    df = transcripts.get_transcripts_list()

    if df.empty:
        return {
            "symbol": symbol,
            "rows_returned": 0,
            "transcripts": []
        }

    result_df = df[
        ["fiscal_year", "fiscal_quarter", "report_date"]
    ].copy()

    return {
        "symbol": symbol,
        "rows_returned": len(result_df),
        "transcripts": result_df.to_dict(orient="records")
    }


def get_stock_earning_call_transcript(
    symbol: str,
    fiscal_year: int,
    fiscal_quarter: int
):
    """
    Retrieve the full earnings call transcript for a specific fiscal period.

    This tool returns the complete transcript content for a given fiscal
    year and quarter, including speaker attribution and paragraph order.

    Args:
        symbol (str): Stock ticker symbol (e.g., "TSLA").
        fiscal_year (int): Fiscal year (e.g., 2024).
        fiscal_quarter (int): Fiscal quarter (1–4).

    Returns:
        dict: A dictionary with the following structure:
            {
                "symbol": "TSLA",
                "fiscal_year": 2024,
                "fiscal_quarter": 4,
                "paragraphs": [
                    {
                        "paragraph_number": 1,
                        "speaker": "Operator",
                        "content": "Good afternoon, everyone and welcome to..."
                    },
                    ...
                ]
            }

    Notes:
        - Transcript content can be large and may consume many tokens.
        - Intended for summarization, Q&A, or qualitative analysis
          of management commentary.
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    transcripts = ticker.earning_call_transcripts()
    df = transcripts.get_transcript(fiscal_year, fiscal_quarter)

    if df.empty:
        return {
            "symbol": symbol,
            "fiscal_year": fiscal_year,
            "fiscal_quarter": fiscal_quarter,
            "paragraphs": []
        }

    return {
        "symbol": symbol,
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "paragraphs": df.to_dict(orient="records")
    }
