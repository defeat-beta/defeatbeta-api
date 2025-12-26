from mcp.server.fastmcp import FastMCP

from .tools.officers import get_stock_officers
from .tools.profile import get_stock_profile
from .tools.meta import get_latest_data_update_date
from .tools.price import get_stock_price
from .tools.transcripts import get_stock_earning_call_transcripts_list, get_stock_earning_call_transcript
from .tools.news import get_stock_news

mcp = FastMCP(
    name="Defeat Beta API",
    instructions="""
                    An open-source alternative to Yahoo Finance's market data APIs with higher reliability.
                """,
    website_url="https://github.com/defeat-beta/defeatbeta-api"
)


# Meta / system tools
mcp.tool()(get_latest_data_update_date)

# Stock core data
mcp.tool()(get_stock_profile)
mcp.tool()(get_stock_price)
mcp.tool()(get_stock_officers)

# Earnings
mcp.tool()(get_stock_earning_call_transcripts_list)
mcp.tool()(get_stock_earning_call_transcript)

# News
mcp.tool()(get_stock_news)

def main():
    mcp.run()

if __name__ == "__main__":
    main()