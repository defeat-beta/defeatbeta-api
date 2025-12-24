from mcp.server.fastmcp import FastMCP
from defeatbeta_api.data.ticker import Ticker

mcp = FastMCP("defeatbeta-finance")


@mcp.tool()
def get_stock_price_chunk(
    symbol: str,
    page: int = 1,
    page_size: int = 200,  # 控制每页大小，安全起见别超过300
    sort: str = "asc"  # asc 或 desc
):
    """
    Get a chunk of historical stock price data (paginated).

    Args:
        symbol: Stock ticker symbol, e.g. TSLA, AAPL
        page: Page number (starting from 1)
        page_size: Number of rows per page (recommended <= 200)
        sort: "asc" (oldest first) or "desc" (newest first)
    """
    ticker = Ticker(symbol.upper())
    df = ticker.price()

    if sort == "desc":
        df = df.sort_values('report_date', ascending=False)
    else:
        df = df.sort_values('report_date')

    total_rows = len(df)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    chunk = df.iloc[start_idx:end_idx]

    if chunk.empty:
        return {"symbol": symbol, "message": "No more data."}

    return {
        "symbol": symbol,
        "page": page,
        "page_size": page_size,
        "total_rows": total_rows,
        "has_more": end_idx < total_rows,
        "date_range": f"{chunk['report_date'].min()} to {chunk['report_date'].max()}",
        "data": chunk.to_dict(orient="records"),
    }


def main():
    mcp.run()


if __name__ == "__main__":
    main()
