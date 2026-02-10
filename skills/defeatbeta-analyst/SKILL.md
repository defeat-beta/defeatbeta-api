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

**For detailed parameters and response schemas**, see [defeatbeta-api-reference.md](references/defeatbeta-api-reference.md)

## Common Workflows

For detailed analysis workflows, see [analysis-templates.md](references/analysis-templates.md):

1. **Quick Investment Screening** - Fast evaluation (profile, price, financials, valuation)
2. **Full Fundamental Analysis** - Comprehensive 6-phase analysis (business, financials, profitability, growth, valuation)
3. **Valuation-Focused Analysis** - Determine over/undervaluation (P/E, P/S, P/B, PEG, industry comparison)
4. **Growth Quality Assessment** - Evaluate revenue/earnings sustainability (margins, cash conversion, ROIC)
5. **DuPont Analysis Deep Dive** - Decompose ROE drivers (margin, turnover, leverage)
6. **DCF Model Data Preparation** - Gather inputs for discounted cash flow valuation
7. **Margin Analysis & Peer Comparison** - Operational efficiency and competitive positioning
8. **Earnings Quality Assessment** - Cash vs accrual earnings, FCF quality, working capital
9. **Industry Positioning Analysis** - Company position relative to peers
10. **Quarterly Earnings Analysis** - Deep dive into latest earnings release
11. **DCF Valuation** - Use `get_stock_dcf_analysis` for automated intrinsic value calculation

## Using the APIs

**Key considerations:**
- **Always call `get_latest_data_update_date` first** - establishes data cutoff for relative queries
- Date parameters use "YYYY-MM-DD" format (e.g., "2020-01-01")
- Stock price/valuation APIs limited to **1000 rows** (use date ranges for more data)
- **ROIC and Equity Multiplier not applicable to banks** (check sector in profile)
- Fiscal periods (earnings transcripts) may differ from calendar periods

**For detailed parameters, response schemas, and data definitions**, see [defeatbeta-api-reference.md](references/defeatbeta-api-reference.md)

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

### 12. DCF Model Best Practices

#### Growth Rate Estimation
**Historical Analysis**:
- Review 5-10 years of annual FCF growth using `get_stock_annual_fcf_yoy_growth`
- Review 8-12 quarters of revenue growth using `get_stock_quarterly_revenue_yoy_growth`
- Identify trends: accelerating, stable, or decelerating growth
- Note: Historical growth ≠ future growth, but provides baseline

**Management Guidance**:
- Extract forward-looking statements from latest earnings call transcript
- Look for: revenue targets, margin expansion plans, capex guidance
- Note risks and headwinds mentioned by management
- Cross-reference guidance with historical execution

**Growth Rate Stage Design**:
- **Years 1-5 (Near-term)**: Base on recent trends + management guidance
  - High-growth companies: 15-25% may be reasonable if supported by data
  - Mature companies: 5-10% more typical
  - Consider: new products, market expansion, competitive position
  
- **Years 6-10 (Mid-term)**: Apply mean reversion principle
  - Typically 50-70% of near-term rate
  - Reflects market maturation, increased competition
  - More conservative than near-term assumptions
  
- **Terminal Rate**: Use 10-Year Treasury yield (risk-free rate)
  - Reflects long-term GDP growth
  - Typical range: 2-4%
  - Should be ≤ long-term economic growth rate

#### TTM Metrics Calculation
- **TTM Free Cash Flow**: Sum of most recent 4 quarters from cash flow statement
  - Check: `free_cash_flow` field from `get_stock_quarterly_cash_flow`
  - Ensure FCF is positive; if negative, DCF may not be appropriate
  
- **TTM Revenue**: Sum of most recent 4 quarters from income statement
  - Check: `total_revenue` field from `get_stock_quarterly_income_statement`
  - Used for FCF margin calculation

#### Projection Mechanics
- **Compound Growth Application**: Each year builds on previous year
  - Avoid: Simple percentage of base year
  - Use: Year_N = Year_(N-1) × (1 + Growth_Rate)
  
- **FCF Margin Tracking**: Monitor projected FCF/Revenue ratio
  - If margin expands dramatically (e.g., from 15% to 40%), revisit assumptions
  - Stable or gradually improving margins are more realistic
  
- **Sanity Checks**:
  - Year 10 FCF should be 2-3x TTM FCF for mature companies
  - Year 10 FCF of 5-10x TTM FCF indicates very aggressive growth

#### Terminal Value Calculation
- **Formula**: Terminal Value = Year 10 FCF × (1 + Terminal Rate) / (WACC - Terminal Rate)
- **Sensitivity**: Terminal Value often represents 60-80% of total Enterprise Value
- **Key Check**: WACC must be > Terminal Rate (otherwise infinite value)
- **Conservative Approach**: Use lower terminal rate if uncertain

#### Balance Sheet Adjustments
- **Cash Addition**: Only operating cash; exclude restricted cash if disclosed
  - Use: `cash_cash_equivalents_and_short_term_investments` from balance sheet
  
- **Debt Subtraction**: Use total debt (short-term + long-term)
  - Use: `total_debt` from balance sheet
  - Some analysts also subtract pension liabilities, lease obligations
  
- **Shares Outstanding**: Use most recent diluted shares outstanding
  - From: `get_stock_market_capitalization` → `shares_outstanding` field
  - Use diluted shares, not basic shares

#### Valuation Interpretation
- **Margin of Safety**:
  - 10-20%: Minimal buffer, requires high conviction
  - 20-40%: Reasonable margin, accounts for estimation error
  - >40%: Significant undervaluation OR overly optimistic assumptions
  
- **Sensitivity Analysis**: Test multiple scenarios
  - Base case: Most likely assumptions
  - Bull case: Optimistic growth rates (+2-3% higher)
  - Bear case: Conservative growth rates (-2-3% lower)
  - See how Fair Price changes with different assumptions

- **Cross-Validation**: DCF should align with other valuation methods
  - Compare with P/E, P/S, P/B multiples vs industry
  - If DCF suggests 50% undervaluation but all multiples are at highs, revisit

#### Common Pitfalls to Avoid
- **Overly optimistic growth**: Don't extrapolate peak growth rates indefinitely
- **Ignoring capital intensity**: High-growth may require significant capex
- **Using outdated data**: Always call `get_latest_data_update_date` first
- **Terminal rate > WACC**: Mathematically impossible, check your inputs
- **Negative FCF base**: DCF doesn't work well for unprofitable/cash-burning companies
- **Ignoring macro factors**: Consider industry trends, economic cycle, regulatory changes

#### DCF Report Generation Best Practices
- Present valuation conclusion with clear comparison table
- Validate key assumptions (WACC reasonableness, growth rate justification)
- Show historical FCF margin trends to support projections
- Flag anomalies or concerns explicitly
- Provide 5 bull case reasons and 5 key risks
- End with specific follow-up analysis recommendations
- For detailed reporting templates, see `analysis-templates.md`

### 13. Combining Multiple Metrics
Strong investment candidates typically show:
- **Growth**: Revenue/earnings growing faster than industry
- **Profitability**: Margins improving or above industry avg
- **Efficiency**: ROE/ROA improving over time
- **Valuation**: P/E, P/S below historical average or industry
- **Cash**: FCF growing and positive

### 14. SEC Filing Access
- Use `get_stock_sec_filings` to retrieve filing metadata and URLs
- **CRITICAL**: Always use the `sec_user_agent` field value as User-Agent header when accessing SEC URLs (SEC blocks requests without proper User-Agent)
- Access `filing_url` to read actual filing content
- Supports all standard SEC forms (10-K, 10-Q, 8-K, DEF 14A, 20-F, 6-K, 13F, etc.)

## Templates & Examples

Detailed workflow templates for common analysis tasks:
- [analysis-templates.md](references/analysis-templates.md)