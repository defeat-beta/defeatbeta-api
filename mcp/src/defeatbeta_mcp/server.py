from mcp.server.fastmcp import FastMCP
from defeatbeta_api.data.ticker import Ticker

mcp = FastMCP("defeatbeta-finance")


@mcp.tool()
def get_stock_price(symbol: str):
    """
    Get historical stock price data.

    Args:
        symbol: Stock ticker symbol, e.g. TSLA, AAPL
    """
    ticker = Ticker(symbol)
    df = ticker.price()

    # LLM-friendly output
    return {
        "symbol": symbol,
        "rows": len(df),
        "data": df.tail(20).to_dict(orient="records"),
    }


def main():
    mcp.run()


if __name__ == "__main__":
    main()
