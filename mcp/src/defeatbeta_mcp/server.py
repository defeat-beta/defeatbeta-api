from mcp.server.fastmcp import FastMCP

from .tools.officers import get_stock_officers
from .tools.profile import get_stock_profile
from .tools.meta import get_latest_data_update_date
from .tools.price import get_stock_price
from .tools.transcripts import get_stock_earning_call_transcripts_list, get_stock_earning_call_transcript
from .tools.news import get_stock_news
from .tools.statement import get_stock_quarterly_income_statement, get_stock_annual_income_statement, \
    get_stock_quarterly_balance_sheet, get_stock_annual_balance_sheet, get_stock_quarterly_cash_flow, \
    get_stock_annual_cash_flow
from .tools.breakdown import get_quarterly_revenue_by_segment, get_quarterly_revenue_by_geography
from .tools.margin import get_stock_quarterly_gross_margin, get_stock_annual_gross_margin

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

# Financial Statement
mcp.tool()(get_stock_quarterly_income_statement)
mcp.tool()(get_stock_annual_income_statement)
mcp.tool()(get_stock_quarterly_balance_sheet)
mcp.tool()(get_stock_annual_balance_sheet)
mcp.tool()(get_stock_quarterly_cash_flow)
mcp.tool()(get_stock_annual_cash_flow)

# Revenue Breakdown
mcp.tool()(get_quarterly_revenue_by_segment)
mcp.tool()(get_quarterly_revenue_by_geography)

# Margin
mcp.tool()(get_stock_quarterly_gross_margin)
mcp.tool()(get_stock_annual_balance_sheet)

def main():
    mcp.run()

if __name__ == "__main__":
    main()