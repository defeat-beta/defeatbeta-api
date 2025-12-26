from defeatbeta_api.data.ticker import Ticker
import pandas as pd

def get_stock_news_list(
    symbol: str,
    start_date: str = None,
    end_date: str = None
):
    """
    Retrieve a list of recent news articles related to a given stock symbol.

    This tool returns structured metadata for each news item **without the full article content**.
    Use the `uuid` field to fetch the full content of a specific news article via `get_stock_news`.

    Args:
        symbol (str): Stock ticker symbol (e.g. "AMD", "AAPL", "TSLA").
                      The symbol is case-insensitive and will be converted
                      to uppercase automatically.
        start_date (str, optional): Filter news on or after this date
                                    (YYYY-MM-DD).
        end_date (str, optional): Filter news on or before this date
                                  (YYYY-MM-DD).

    Returns:
        dict: A dictionary containing:
            - symbol (str): Stock ticker symbol
            - date_range (str): Actual date range covered
            - rows_returned (int): Number of news items returned
            - truncated (bool): Whether results were truncated by MAX_ROWS
            - news (list[dict]): List of news metadata records, each including:
                - uuid (str)
                - report_date (str)
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    news = ticker.news()
    df = news.get_news_list()

    if df.empty:
        return {
            "symbol": symbol,
            "rows_returned": 0,
            "truncated": False,
            "news": []
        }

    # Ensure report_date is datetime for filtering
    df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce")
    df = df.sort_values("report_date").reset_index(drop=True)

    # Apply date filters
    if start_date:
        try:
            start_dt = pd.to_datetime(start_date)
            df = df[df["report_date"] >= start_dt]
        except ValueError:
            return {"error": f"Invalid start_date format: '{start_date}'. Use YYYY-MM-DD."}

    if end_date:
        try:
            end_dt = pd.to_datetime(end_date)
            df = df[df["report_date"] <= end_dt]
        except ValueError:
            return {"error": f"Invalid end_date format: '{end_date}'. Use YYYY-MM-DD."}

    if df.empty:
        return {
            "symbol": symbol,
            "rows_returned": 0,
            "truncated": False,
            "news": []
        }

    # Safety cap to avoid LLM token overflow
    MAX_ROWS = 500
    if len(df) > MAX_ROWS:
        df = df.tail(MAX_ROWS)  # keep the most recent news
        truncated = True
    else:
        truncated = False

    # Select only MCP / LLM friendly fields
    fields = [
        "uuid",
        "report_date"
    ]

    records = df[fields].copy()
    records["report_date"] = records["report_date"].dt.strftime("%Y-%m-%d")

    return {
        "symbol": symbol,
        "date_range": f"{records['report_date'].iloc[0]} to {records['report_date'].iloc[-1]}",
        "rows_returned": len(records),
        "truncated": truncated,
        "news": records.to_dict(orient="records"),
    }


def get_stock_news(symbol: str, uuid: str):
    """
    Retrieve the full content of a specific news article by UUID.

    This tool returns both the news metadata and the full article content,
    structured by paragraphs. It is suitable for detailed reading,
    summarization, sentiment analysis, and extracting key information
    from a single news item.

    Args:
        symbol (str): Stock ticker symbol (e.g. "AMD", "AAPL", "TSLA").
                      The symbol is case-insensitive and will be converted
                      to uppercase automatically.
        uuid (str): Unique identifier of the news article, obtained from
                    `get_stock_news_list`.

    Returns:
        dict: A dictionary containing:
            - symbol (str): Stock ticker symbol
            - uuid (str): News UUID
            - title (str): News title
            - publisher (str): News publisher
            - report_date (str): News publish date (YYYY-MM-DD)
            - type (str): News type (e.g. STORY, PRESS_RELEASE)
            - link (str): Original news link
            - related_symbols (list[str]): Related stock symbols
            - paragraphs (list[dict]): Full news content split into paragraphs,
              each paragraph includes:
                - paragraph_number (int)
                - speaker (str, optional)
                - paragraph (str)
                - highlight (str, optional)
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    news = ticker.news()
    df = news.get_news(uuid)

    if df.empty:
        return {
            "symbol": symbol,
            "uuid": uuid,
            "message": "No news content found for the specified UUID."
        }

    row = df.iloc[0]

    return {
        "symbol": symbol,
        "uuid": row.get("uuid"),
        "title": row.get("title"),
        "publisher": row.get("publisher"),
        "report_date": row.get("report_date"),
        "type": row.get("type"),
        "link": row.get("link"),
        "related_symbols": row.get("related_symbols"),
        "paragraphs": row.get("news"),
    }
