from defeatbeta_api.data.ticker import Ticker

def get_stock_news_list(symbol: str):
    """
    Retrieve a list of recent news related to a given stock symbol.

    This tool returns structured metadata for each news item without
    including the full article content. It is suitable for browsing,
    filtering, ranking, or selecting specific news articles for further
    analysis.

    Args:
        symbol (str): Stock ticker symbol (e.g. "AMD", "AAPL", "TSLA").
                      The symbol is case-insensitive and will be converted
                      to uppercase automatically.

    Returns:
        dict: A dictionary containing:
            - symbol (str): Stock ticker symbol
            - rows_returned (int): Number of news items returned
            - news (list[dict]): List of news metadata records, each including:
                - uuid (str): Unique identifier of the news item
                - related_symbols (list[str]): Related stock symbols
                - title (str): News title
                - publisher (str): News publisher
                - report_date (str): News publish date (YYYY-MM-DD)
                - type (str): News type (e.g. STORY, PRESS_RELEASE)
                - link (str): Original news link
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    news = ticker.news()
    df = news.get_news_list()

    if df.empty:
        return {
            "symbol": symbol,
            "rows_returned": 0,
            "news": []
        }

    # Select only MCP / LLM friendly fields
    fields = [
        "uuid",
        "related_symbols",
        "title",
        "publisher",
        "report_date",
        "type",
        "link",
    ]

    records = df[fields].to_dict(orient="records")

    return {
        "symbol": symbol,
        "rows_returned": len(records),
        "news": records
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
