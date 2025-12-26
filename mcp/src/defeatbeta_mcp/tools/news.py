from defeatbeta_api.data.ticker import Ticker
import pandas as pd

def get_stock_news(symbol: str, start_date: str = None, end_date: str = None, max_rows: int = 50):
    """
    Retrieve recent news articles for a given stock symbol, including full content.

    This tool returns a list of news items with metadata and paragraph-level content.
    Suitable for reading, summarization, sentiment analysis, or extracting key information.

    Args:
        symbol (str): Stock ticker symbol (e.g., "AMD", "AAPL", "TSLA").
                      Case-insensitive; will be converted to uppercase.
        start_date (str, optional): Filter news on or after this date (YYYY-MM-DD).
        end_date (str, optional): Filter news on or before this date (YYYY-MM-DD).
        max_rows (int, optional): Maximum number of news items to return (default 50).

    Returns:
        dict: {
            "symbol": str,
            "date_range": str,  # actual date range covered
            "rows_returned": int,
            "truncated": bool,
            "news": [
                {
                    "uuid": str,
                    "report_date": str,
                    "title": str,
                    "publisher": str,
                    "type": str,
                    "link": str,
                    "related_symbols": list[str],
                    "paragraphs": [
                        {
                            "paragraph_number": int,
                            "paragraph": str,
                            "highlight": str  # optional
                        },
                        ...
                    ]
                },
                ...
            ]
        }
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)
    news = ticker.news()
    df = news.get_news_list()

    if df.empty:
        return {"symbol": symbol, "rows_returned": 0, "truncated": False, "news": []}

    df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce")
    df = df.sort_values("report_date").reset_index(drop=True)

    if start_date:
        try:
            start_dt = pd.to_datetime(start_date)
            df = df[df["report_date"] >= start_dt]
        except ValueError:
            return {"error": f"Invalid start_date: {start_date}"}
    if end_date:
        try:
            end_dt = pd.to_datetime(end_date)
            df = df[df["report_date"] <= end_dt]
        except ValueError:
            return {"error": f"Invalid end_date: {end_date}"}

    if df.empty:
        return {"symbol": symbol, "rows_returned": 0, "truncated": False, "news": []}

    truncated = False
    if len(df) > max_rows:
        df = df.tail(max_rows)
        truncated = True

    news_items = []
    for _, row in df.iterrows():
        news_content = news.get_news(row["uuid"])
        paragraphs = []
        if not news_content.empty:
            paragraphs = [
                {
                    "paragraph_number": p.get("paragraph_number"),
                    "paragraph": p.get("paragraph"),
                    "highlight": p.get("highlight", "")
                }
                for p in news_content.iloc[0].get("news", [])
            ]
        news_items.append({
            "uuid": row["uuid"],
            "report_date": row["report_date"].strftime("%Y-%m-%d"),
            "title": row.get("title"),
            "publisher": row.get("publisher"),
            "type": row.get("type"),
            "link": row.get("link"),
            "related_symbols": row.get("related_symbols", []),
            "paragraphs": paragraphs
        })

    return {
        "symbol": symbol,
        "date_range": f"{df['report_date'].iloc[0].strftime('%Y-%m-%d')} to {df['report_date'].iloc[-1].strftime('%Y-%m-%d')}",
        "rows_returned": len(news_items),
        "truncated": truncated,
        "news": news_items
    }
