---
name: defeatbeta-analyst
description: "Comprehensive financial analysis using 60+ data endpoints. Analyze company fundamentals, financial statements, valuation metrics, profitability ratios, growth trends, and industry comparisons. Use for: (1) fundamental analysis and DCF modeling, (2) financial statement analysis, (3) valuation and ratio analysis, (4) growth and profitability assessment, (5) industry benchmarking, or any deep financial research tasks."
---

# Financial Analyst

Professional-grade financial analysis using historical market data and comprehensive financial metrics from the defeatbeta dataset.

## Core Capabilities

- **Market Data**: S&P 500 returns, Treasury yields, stock prices, market cap, beta
- **Company Intelligence**: Profiles, executives, SEC filings, earnings transcripts, news
- **Financial Statements**: Income statement, balance sheet, cash flow (quarterly & annual)
- **Valuation Metrics**: P/E, P/S, P/B, PEG ratios, market cap, WACC
- **Profitability Analysis**: Margins (gross, operating, net, EBITDA, FCF), ROE, ROA, ROIC
- **Growth Analysis**: YoY growth for revenue, earnings, EBITDA, FCF, EPS
- **Segment Analysis**: Revenue by business segment and geography
- **Industry Benchmarking**: Compare against industry averages for all metrics
- **DuPont Analysis**: Equity multiplier, asset turnover decomposition

## Dataset Reference Date

**CRITICAL**: Always call `get_latest_data_update_date` at the start of analysis to determine the data cutoff date. This is the "today" for all relative time queries (e.g., "last 10 days", "past quarter", "YTD").

## Available APIs

### Market & Macro Data
- `get_latest_data_update_date` - **ALWAYS call first** - Get data cutoff date
- `get_sp500_historical_annual_returns` - S&P 500 annual returns since 1928
- `get_sp500_cagr_returns` - S&P 500 CAGR for N years
- `get_sp500_cagr_returns_rolling` - Rolling N-year CAGR periods
- `get_daily_treasury_yield` - Daily Treasury yield curve (1m-30y maturities)

### Company Information
- `get_stock_profile` - Company profile, industry, sector, business summary
- `get_stock_officers` - Executive team with compensation data
- `get_stock_sec_filings` - SEC filing history (10-K, 10-Q, 8-K, etc.)
- `get_stock_earning_call_transcripts_list` - Available earnings call metadata
- `get_stock_earning_call_transcript` - Full transcript by fiscal period
- `get_stock_news` - Historical news with full article content

### Price & Market Data
- `get_stock_price` - Historical daily OHLCV data (max 1000 rows)
- `get_stock_eps_and_ttm_eps` - Quarterly EPS and TTM EPS
- `get_stock_market_capitalization` - Historical market cap
- `get_stock_ttm_pe` - Historical TTM P/E ratio
- `get_stock_wacc` - Weighted Average Cost of Capital

### Financial Statements (Quarterly & Annual)
- `get_stock_quarterly_income_statement` / `get_stock_annual_income_statement`
- `get_stock_quarterly_balance_sheet` / `get_stock_annual_balance_sheet`
- `get_stock_quarterly_cash_flow` / `get_stock_annual_cash_flow`

### Segment Analysis
- `get_quarterly_revenue_by_segment` - Revenue breakdown by business segment
- `get_quarterly_revenue_by_geography` - Revenue breakdown by region

### Profitability Margins (Quarterly & Annual)
- `get_stock_quarterly_gross_margin` / `get_stock_annual_gross_margin`
- `get_stock_quarterly_operating_margin` / `get_stock_annual_operating_margin`
- `get_stock_quarterly_net_margin` / `get_stock_annual_net_margin`
- `get_stock_quarterly_ebitda_margin` / `get_stock_annual_ebitda_margin`
- `get_stock_quarterly_fcf_margin` / `get_stock_annual_fcf_margin`

### Profitability Ratios (Quarterly)
- `get_stock_quarterly_roe` - Return on Equity
- `get_stock_quarterly_roa` - Return on Assets
- `get_stock_quarterly_roic` - Return on Invested Capital (**Not for banks**)
- `get_stock_quarterly_equity_multiplier` - Financial leverage (**Not for banks**)
- `get_stock_quarterly_asset_turnover` - Asset efficiency

### Valuation Ratios
- `get_stock_ps_ratio` - Price-to-Sales ratio (max 1000 rows)
- `get_stock_pb_ratio` - Price-to-Book ratio (max 1000 rows)
- `get_stock_peg_ratio` - PEG by earnings & revenue growth (max 1000 rows)

### Growth Metrics (Quarterly & Annual)
- `get_stock_quarterly_revenue_yoy_growth` / `get_stock_annual_revenue_yoy_growth`
- `get_stock_quarterly_operating_income_yoy_growth` / `get_stock_annual_operating_income_yoy_growth`
- `get_stock_quarterly_ebitda_yoy_growth` / `get_stock_annual_ebitda_yoy_growth`
- `get_stock_quarterly_net_income_yoy_growth` / `get_stock_annual_net_income_yoy_growth`
- `get_stock_quarterly_fcf_yoy_growth` / `get_stock_annual_fcf_yoy_growth`
- `get_stock_quarterly_diluted_eps_yoy_growth` - Quarterly EPS growth
- `get_stock_quarterly_ttm_diluted_eps_yoy_growth` - TTM EPS growth

### Industry Benchmarking
- `get_industry_quarterly_gross_margin` - Industry gross margin
- `get_industry_quarterly_net_margin` - Industry net margin
- `get_industry_quarterly_ebitda_margin` - Industry EBITDA margin
- `get_industry_ttm_pe` - Industry P/E ratio (max 1000 rows)
- `get_industry_ps_ratio` - Industry P/S ratio (max 1000 rows)
- `get_industry_pb_ratio` - Industry P/B ratio (max 1000 rows)
- `get_industry_quarterly_roe` - Industry ROE
- `get_industry_quarterly_roa` - Industry ROA
- `get_industry_quarterly_equity_multiplier` - Industry leverage
- `get_industry_quarterly_asset_turnover` - Industry asset efficiency

## Common Workflows

### 1. Quick Company Overview
```
User: "Give me a quick overview of TSLA"
→ get_latest_data_update_date (get reference date)
→ get_stock_profile (company info)
→ get_stock_price (recent performance, last 90 days)
→ get_stock_quarterly_income_statement (latest revenue/earnings)
→ get_stock_ttm_pe (current valuation)
```

### 2. Comprehensive Fundamental Analysis
```
User: "Perform fundamental analysis on AAPL"
→ get_latest_data_update_date
→ get_stock_profile (business context)
→ get_stock_quarterly_income_statement (revenue trends)
→ get_stock_quarterly_balance_sheet (financial position)
→ get_stock_quarterly_cash_flow (cash generation)
→ get_stock_quarterly_gross_margin (profitability)
→ get_stock_quarterly_roe (return metrics)
→ get_stock_quarterly_revenue_yoy_growth (growth trajectory)
→ get_stock_ttm_pe (valuation)
→ get_industry_ttm_pe (peer comparison)
```

### 3. Valuation Analysis
```
User: "Is NVDA overvalued?"
→ get_latest_data_update_date
→ get_stock_ttm_pe (historical P/E trend)
→ get_stock_ps_ratio (P/S analysis)
→ get_stock_pb_ratio (P/B analysis)
→ get_stock_peg_ratio (growth-adjusted valuation)
→ get_industry_ttm_pe (industry benchmark)
→ get_industry_ps_ratio (industry P/S)
→ get_stock_quarterly_revenue_yoy_growth (growth justification)
→ get_stock_quarterly_net_margin (profitability check)
```

### 4. Profitability & Efficiency Analysis
```
User: "Analyze AMZN's profitability trends"
→ get_latest_data_update_date
→ get_stock_quarterly_gross_margin (margin expansion/contraction)
→ get_stock_quarterly_operating_margin (operational efficiency)
→ get_stock_quarterly_net_margin (bottom-line profitability)
→ get_stock_quarterly_fcf_margin (cash generation)
→ get_stock_quarterly_roe (shareholder returns)
→ get_stock_quarterly_roa (asset efficiency)
→ get_industry_quarterly_gross_margin (vs industry)
→ get_industry_quarterly_net_margin (vs industry)
```

### 5. Growth Assessment
```
User: "What's the growth trajectory for AMD?"
→ get_latest_data_update_date
→ get_stock_quarterly_revenue_yoy_growth (top-line growth)
→ get_stock_quarterly_operating_income_yoy_growth (operational leverage)
→ get_stock_quarterly_net_income_yoy_growth (earnings growth)
→ get_stock_quarterly_fcf_yoy_growth (cash flow growth)
→ get_stock_quarterly_ttm_diluted_eps_yoy_growth (EPS momentum)
→ get_quarterly_revenue_by_segment (growth drivers)
```

### 6. DCF Model Preparation
```
User: "Prepare data for MSFT DCF model"
→ get_latest_data_update_date
→ get_stock_quarterly_cash_flow (historical FCF)
→ get_stock_quarterly_revenue_yoy_growth (growth rate)
→ get_stock_wacc (discount rate)
→ get_sp500_cagr_returns (market return, 10y)
→ get_daily_treasury_yield (risk-free rate)
→ get_stock_quarterly_balance_sheet (terminal value inputs)
→ get_stock_market_capitalization (current valuation)
```

### 7. DuPont Analysis
```
User: "Perform DuPont analysis on JPM"
→ get_latest_data_update_date
→ get_stock_quarterly_roe (ROE = target metric)
→ get_stock_quarterly_roa (ROA component)
→ get_stock_quarterly_net_margin (Net Margin component)
→ get_stock_quarterly_asset_turnover (Asset Turnover component)
→ get_stock_quarterly_equity_multiplier (Leverage component)
→ Compare: ROE = Net Margin × Asset Turnover × Equity Multiplier
```

### 8. Industry Peer Comparison
```
User: "Compare TSLA margins to auto industry"
→ get_latest_data_update_date
→ get_stock_profile (confirm industry)
→ get_stock_quarterly_gross_margin (TSLA margins)
→ get_stock_quarterly_operating_margin
→ get_stock_quarterly_net_margin
→ get_industry_quarterly_gross_margin (industry avg)
→ get_industry_quarterly_net_margin (industry avg)
→ get_stock_quarterly_roe (TSLA profitability)
→ get_industry_quarterly_roe (industry profitability)
```

### 9. Earnings Deep Dive
```
User: "Analyze META's latest earnings"
→ get_latest_data_update_date
→ get_stock_earning_call_transcripts_list (find latest)
→ get_stock_earning_call_transcript (read full call)
→ get_stock_quarterly_income_statement (verify numbers)
→ get_stock_quarterly_revenue_yoy_growth (growth context)
→ get_stock_quarterly_operating_margin (margin trends)
→ get_stock_news (recent developments)
```

### 10. SEC Filing Analysis
```
User: "What did NFLX report in their latest 10-K?"
→ get_latest_data_update_date
→ get_stock_sec_filings (find latest 10-K)
→ Present filing URL for user review
→ get_stock_quarterly_income_statement (quantitative summary)
→ get_stock_quarterly_balance_sheet (financial position)
→ get_quarterly_revenue_by_segment (segment performance)
```

## Key Parameters

### Date Range Parameters
- `start_date` / `end_date`: "YYYY-MM-DD" format (e.g., "2020-01-01")
- **Always reference data cutoff from `get_latest_data_update_date`**
- For relative queries ("last 10 days"), calculate from data cutoff date

### Symbol Parameters
- `symbol`: Stock ticker (e.g., "TSLA", "AAPL") - case insensitive

### Fiscal Period Parameters (Earnings Transcripts)
- `fiscal_year`: Integer (e.g., 2024)
- `fiscal_quarter`: 1-4
- **Important**: Fiscal periods may differ from calendar periods

### Data Limits
- Stock price, market cap, valuation ratios: **MAX 1000 rows** (truncated if exceeded)
- SEC filings: **MAX 500 rows** (truncated if exceeded)
- News: **MAX rows configurable via `max_rows` parameter** (default 50)
- Use multiple calls with date ranges for larger datasets

### Other Parameters
- `years`: For CAGR calculations (e.g., 10)
- `max_rows`: For news API (1-∞, default 50)

## Key Data Points

### Profile Data
- Business summary, industry, sector
- Full-time employees
- Address, phone, website
- Report date

### Financial Statement Data
- All standard line items (revenue, COGS, operating expenses, etc.)
- Currency information
- Period type (quarterly/annual)
- Null handling for missing data

### Margin Metrics
- Gross margin = Gross Profit / Revenue
- Operating margin = Operating Income / Revenue
- Net margin = Net Income / Revenue
- EBITDA margin = EBITDA / Revenue
- FCF margin = Free Cash Flow / Revenue

### Profitability Ratios
- ROE = Net Income / Average Equity
- ROA = Net Income / Average Assets
- ROIC = NOPAT / Average Invested Capital (**Not for banks**)
- Asset Turnover = ROA / Net Margin
- Equity Multiplier = ROE / ROA (**Not for banks**)

### Valuation Metrics
- TTM P/E = Market Cap / TTM Net Income
- P/S = Market Cap / TTM Revenue
- P/B = Market Cap / Book Value of Equity
- PEG = (P/E) / Growth Rate

### WACC Components
- Weight of Debt, Weight of Equity
- Cost of Debt, Cost of Equity
- Tax Rate, Beta (5-year)
- Risk-Free Rate (10-year Treasury)
- Expected Market Return (10-year S&P 500 CAGR)

### Growth Metrics
- YoY Growth = (Current - Prior Year) / Prior Year
- Available for: Revenue, Operating Income, EBITDA, Net Income, FCF, EPS

### Segment Data
- Revenue by business segment (quarterly)
- Revenue by geography (quarterly)
- Currency: USD

## When to Use This Skill

**ALWAYS invoke this skill when users request:**

### Company Analysis
- "Analyze [COMPANY]", "fundamental analysis", "company overview"
- "Tell me about [COMPANY]'s business", "what does [COMPANY] do"
- "How is [COMPANY] performing", "financial health"

### Financial Statements
- "Income statement", "balance sheet", "cash flow statement"
- "Revenue", "earnings", "profit", "assets", "liabilities", "cash"
- "Quarterly/annual financials"

### Valuation
- "Is [STOCK] overvalued/undervalued", "fair value", "valuation"
- "P/E ratio", "price-to-sales", "price-to-book", "PEG ratio"
- "Market cap", "enterprise value"

### Profitability
- "Margins", "profitability", "ROE", "ROA", "ROIC"
- "How profitable is [COMPANY]"
- "Operating efficiency", "return on investment"

### Growth
- "Growth rate", "revenue growth", "earnings growth"
- "Is [COMPANY] growing", "growth trajectory"
- "YoY growth", "year-over-year"

### Industry Comparison
- "Compare to industry", "industry average", "peer comparison"
- "How does [COMPANY] compare to competitors"
- "Industry benchmarking"

### DCF & Modeling
- "DCF model", "discounted cash flow", "intrinsic value"
- "WACC", "cost of capital", "discount rate"
- "Terminal value", "free cash flow projection"

### Earnings & News
- "Earnings call", "earnings transcript", "what did management say"
- "Recent news", "latest developments"
- "SEC filing", "10-K", "10-Q", "8-K"

## Best Practices

### 1. Always Start with Data Cutoff Date
**CRITICAL**: Call `get_latest_data_update_date` at the beginning of every analysis session. Use this as "today" for all relative time calculations.

### 2. Context-Appropriate Timeframes
- **Quick check**: Last 4 quarters (1 year)
- **Trend analysis**: Last 8-12 quarters (2-3 years)
- **Long-term patterns**: Last 20 quarters (5 years)
- **Valuation history**: 3-5 years for P/E, P/S trends

### 3. Quarterly vs Annual
- Use **quarterly** for recent trends and momentum
- Use **annual** for long-term patterns and stability
- Quarterly data is more current but more volatile

### 4. Industry Benchmarking
Always compare company metrics against industry averages:
- Margins: Is the company more/less efficient than peers?
- Profitability: ROE/ROA relative to industry
- Valuation: P/E, P/S relative to industry multiples

### 5. Handling Data Limits
When APIs return `truncated: true`:
- Make multiple calls with narrower date ranges
- Prioritize most recent data for current analysis
- Use annual data for longer historical views

### 6. Bank vs Non-Bank Companies
- **ROIC**: Not applicable to banks (skip for financial institutions)
- **Equity Multiplier**: Not applicable to banks
- Check `sector` in profile to identify financial companies

### 7. Segment Analysis
- Use segment data to identify growth drivers
- Geographic breakdown reveals market concentration
- Compare segment margins when available

### 8. Fiscal vs Calendar Periods
- Earnings transcripts use fiscal periods (may differ from calendar)
- Always specify both `fiscal_year` and `fiscal_quarter`
- Cross-reference with financial statement periods

### 9. Growth Interpretation
- Positive YoY growth = expansion
- Negative YoY growth = contraction
- Compare growth rates: revenue vs earnings vs FCF
- Earnings growing faster than revenue = margin expansion

### 10. DuPont Decomposition
Validate the DuPont identity:
- ROE = Net Margin × Asset Turnover × Equity Multiplier
- ROE = ROA × Equity Multiplier
- Asset Turnover = ROA / Net Margin

### 11. WACC for DCF
- Use `get_stock_wacc` for discount rate
- Cross-check components: beta, risk-free rate, market return
- Consider using 10-year Treasury as risk-free rate
- Use 10-year S&P 500 CAGR as expected market return

### 12. Combining Multiple Metrics
Strong investment candidates typically show:
- **Growth**: Revenue/earnings growing faster than industry
- **Profitability**: Margins improving or above industry avg
- **Efficiency**: ROE/ROA improving over time
- **Valuation**: P/E, P/S below historical average or industry
- **Cash**: FCF growing and positive

## API Reference

Full parameter specifications and response schemas:
- [defeatbeta-api-reference.md](references/defeatbeta-api-reference.md)

## Templates & Examples

Detailed workflow templates for common analysis tasks:
- [analysis-templates.md](references/analysis-templates.md)