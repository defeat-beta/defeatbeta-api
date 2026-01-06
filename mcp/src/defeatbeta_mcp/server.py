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
from .tools.margin import get_stock_quarterly_gross_margin, get_stock_annual_gross_margin, \
    get_stock_quarterly_operating_margin, get_stock_annual_operating_margin, \
    get_stock_quarterly_net_margin, get_stock_annual_net_margin, \
    get_stock_quarterly_ebitda_margin, get_stock_annual_ebitda_margin, \
    get_stock_quarterly_fcf_margin, get_stock_annual_fcf_margin, \
    get_industry_quarterly_gross_margin, get_industry_quarterly_net_margin, get_industry_quarterly_ebitda_margin
from .tools.eps import get_stock_eps_and_ttm_eps
from .tools.pe import get_stock_ttm_pe, get_industry_ttm_pe
from .tools.cap import get_stock_market_capitalization
from .tools.ps import get_stock_ps_ratio, get_industry_ps_ratio
from .tools.pb import get_stock_pb_ratio, get_industry_pb_ratio
from .tools.peg import get_stock_peg_ratio
from .tools.roe import get_stock_quarterly_roe, get_industry_quarterly_roe
from .tools.roa import get_stock_quarterly_roa, get_industry_quarterly_roa
from .tools.roic import get_stock_quarterly_roic
from .tools.em import get_stock_quarterly_equity_multiplier, get_industry_quarterly_equity_multiplier
from .tools.asserts import get_stock_quarterly_asset_turnover, get_industry_quarterly_asset_turnover
from .tools.growth import get_stock_quarterly_revenue_yoy_growth, get_stock_annual_revenue_yoy_growth, \
    get_stock_quarterly_operating_income_yoy_growth, get_stock_annual_operating_income_yoy_growth, \
    get_stock_quarterly_ebitda_yoy_growth, get_stock_annual_ebitda_yoy_growth, \
    get_stock_quarterly_net_income_yoy_growth, get_stock_annual_net_income_yoy_growth

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
mcp.tool()(get_stock_annual_gross_margin)
mcp.tool()(get_stock_quarterly_operating_margin)
mcp.tool()(get_stock_annual_operating_margin)
mcp.tool()(get_stock_quarterly_net_margin)
mcp.tool()(get_stock_annual_net_margin)
mcp.tool()(get_stock_quarterly_ebitda_margin)
mcp.tool()(get_stock_annual_ebitda_margin)
mcp.tool()(get_stock_quarterly_fcf_margin)
mcp.tool()(get_stock_annual_fcf_margin)
mcp.tool()(get_industry_quarterly_gross_margin)
mcp.tool()(get_industry_quarterly_net_margin)
mcp.tool()(get_industry_quarterly_ebitda_margin)

# Value
mcp.tool()(get_stock_eps_and_ttm_eps)
mcp.tool()(get_stock_ttm_pe)
mcp.tool()(get_stock_market_capitalization)
mcp.tool()(get_stock_ps_ratio)
mcp.tool()(get_stock_pb_ratio)
mcp.tool()(get_stock_peg_ratio)
mcp.tool()(get_stock_quarterly_roe)
mcp.tool()(get_stock_quarterly_roa)
mcp.tool()(get_stock_quarterly_roic)
mcp.tool()(get_stock_quarterly_equity_multiplier)
mcp.tool()(get_stock_quarterly_asset_turnover)
mcp.tool()(get_industry_ttm_pe)
mcp.tool()(get_industry_ps_ratio)
mcp.tool()(get_industry_pb_ratio)
mcp.tool()(get_industry_quarterly_roe)
mcp.tool()(get_industry_quarterly_roa)
mcp.tool()(get_industry_quarterly_equity_multiplier)
mcp.tool()(get_industry_quarterly_asset_turnover)

# Growth
mcp.tool()(get_stock_quarterly_revenue_yoy_growth)
mcp.tool()(get_stock_annual_revenue_yoy_growth)
mcp.tool()(get_stock_quarterly_operating_income_yoy_growth)
mcp.tool()(get_stock_annual_operating_income_yoy_growth)
mcp.tool()(get_stock_quarterly_ebitda_yoy_growth)
mcp.tool()(get_stock_annual_ebitda_yoy_growth)
mcp.tool()(get_stock_quarterly_net_income_yoy_growth)
mcp.tool()(get_stock_annual_net_income_yoy_growth)

def main():
    mcp.run()

if __name__ == "__main__":
    main()