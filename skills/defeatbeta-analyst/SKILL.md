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

### 6. DCF (Discounted Cash Flow) Valuation Model
```
User: "Build a DCF model for TSLA" or "What's the fair value of AAPL using DCF?"

PHASE 1: Data Collection
→ get_latest_data_update_date (reference date)
→ get_stock_profile (company background)
→ get_stock_price (latest close price for Current Price, last 30 days)
→ get_stock_quarterly_cash_flow (get TTM Free Cash Flow)
→ get_stock_quarterly_income_statement (get TTM Revenue)

PHASE 2: Historical Growth Analysis (for Growth Estimates)
→ get_stock_annual_fcf_yoy_growth (show FCF growth trends, last 5-10 years)
→ get_stock_quarterly_revenue_yoy_growth (show Revenue growth trends, last 8-12 quarters)
→ Display both datasets in detail so user can see historical growth patterns

PHASE 3: Management Outlook & Market Intelligence
→ get_stock_earning_call_transcripts_list (find recent earnings calls)
→ get_stock_earning_call_transcript (latest call - management's forward guidance)
→ get_stock_news (recent 3-6 months news for business developments)
→ Summarize: management's growth expectations, new products/markets, risks

PHASE 4: Growth Rate Estimates (THREE STAGES)
Based on PHASE 2 + PHASE 3 analysis, propose:
1. Near-term Growth (Years 1-5):
   - Synthesize: historical FCF growth + management guidance + news sentiment
   - Typically higher growth phase
   
2. Mid-term Growth (Years 6-10):
   - Conservative slowdown from near-term
   - Consider market maturity, competition
   
3. Terminal Growth Rate:
   → get_daily_treasury_yield (use latest 10-Year Treasury yield)
   - Terminal rate = Risk-Free Rate (perpetual growth assumption)

PHASE 5: Discount Rate (WACC)
→ get_stock_wacc (get latest WACC for discount rate)
→ Display WACC components: Cost of Equity, Cost of Debt, Capital Structure

PHASE 6: Free Cash Flow Projection (10-Year Forecast)
Using TTM FCF from PHASE 1 as base:
- Years 1-5: Apply "Near-term Growth Rate"
  - Year 1 FCF = TTM FCF × (1 + Near-term Growth Rate)
  - Year 2 FCF = Year 1 FCF × (1 + Near-term Growth Rate)
  - ... continue through Year 5
  
- Years 6-10: Apply "Mid-term Growth Rate"
  - Year 6 FCF = Year 5 FCF × (1 + Mid-term Growth Rate)
  - ... continue through Year 10

PHASE 7: Revenue Projection (for FCF Margin calculation)
Using TTM Revenue from PHASE 1 as base:
- Apply same growth rates as FCF projection
- Years 1-5: Near-term Revenue Growth Rate
- Years 6-10: Mid-term Revenue Growth Rate
- Calculate: FCF Margin = Projected FCF / Projected Revenue (for each year)

PHASE 8: Present Value of Projected FCF
For each year 1-10:
- PV(Year N FCF) = Year N FCF / (1 + WACC)^N
- Sum all PV values

PHASE 9: Terminal Value Calculation
- Terminal FCF = Year 10 FCF × (1 + Terminal Growth Rate)
- Terminal Value = Terminal FCF / (WACC - Terminal Growth Rate)
- PV of Terminal Value = Terminal Value / (1 + WACC)^10

PHASE 10: Enterprise Value → Equity Value → Fair Price
→ get_stock_quarterly_balance_sheet (latest quarter)
  - Extract: cash_cash_equivalents_and_short_term_investments
  - Extract: total_debt
  
→ get_stock_market_capitalization (latest data)
  - Extract: shares_outstanding

Calculate:
1. Enterprise Value (EV) = Sum of PV(FCF Years 1-10) + PV(Terminal Value)
2. Equity Value = EV + Cash & Equivalents - Total Debt
3. Fair Price = Equity Value / Outstanding Shares

PHASE 11: Valuation Assessment
Compare:
- Fair Price (DCF output)
- Current Price (latest close from PHASE 1)
- Margin of Safety = (Fair Price - Current Price) / Fair Price × 100%

Interpretation:
- If Fair Price > Current Price → potentially undervalued
- If Fair Price < Current Price → potentially overvalued
- Margin of Safety > 20-30% → significant upside potential
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
→ access `filing_url` to read actual filing content 
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

### 13. Combining Multiple Metrics
Strong investment candidates typically show:
- **Growth**: Revenue/earnings growing faster than industry
- **Profitability**: Margins improving or above industry avg
- **Efficiency**: ROE/ROA improving over time
- **Valuation**: P/E, P/S below historical average or industry
- **Cash**: FCF growing and positive

### 14. SEC Filing Access
When analyzing SEC filings:
- Use `get_stock_sec_filings` to retrieve filing metadata and URLs
- **CRITICAL**: Always use the `sec_user_agent` field value as User-Agent header when accessing SEC URLs (SEC blocks requests without proper User-Agent)
- Access `filing_url` to read actual filing content
- Supported form types include:
  - **US Domestic Company Forms:**
    - `10-K`, `10-K/A` - Annual report
    - `10-Q`, `10-Q/A` - Quarterly report
    - `8-K`, `8-K/A` - Current report (material events)
    - `DEF 14A`, `DEFA14A` - Proxy statement (shareholder meetings, executive compensation)
  - **Insider Trading Forms:**
    - `3`, `3/A` - Initial beneficial ownership
    - `4`, `4/A` - Changes in beneficial ownership
    - `5`, `5/A` - Annual beneficial ownership
    - `144`, `144/A` - Notice of proposed sale of securities
  - **Institutional Holdings:**
    - `13F-HR`, `13F-HR/A` - Institutional holdings report (quarterly)
    - `SC 13G`, `SC 13G/A` - Passive investor holdings (>5%)
    - `SC 13D`, `SC 13D/A` - Active investor holdings (>5%, may influence company)
  - **Foreign Private Issuer Forms** (e.g., BABA, PDD, JD):
    - `20-F`, `20-F/A` - Annual report
    - `6-K`, `6-K/A` - Current report (quarterly + material events)
  - **Canadian Company Forms** (e.g., SHOP, TD, RY):
    - `40-F`, `40-F/A` - Annual report
  - **ETF/Investment Company Forms** (e.g., SPY, QQQ, VOO):
    - `N-CSR`, `N-CSR/A` - Annual/Semi-annual shareholder report
    - `N-CSRS`, `N-CSRS/A` - Semi-annual shareholder report
    - `N-30D`, `N-30D/A` - Shareholder report (legacy format)
    - `NPORT-P` - Monthly portfolio holdings
    - `N-CEN` - Annual report (fund operations)
    - `N-Q`, `N-Q/A` - Quarterly portfolio (discontinued, historical data exists)

## API Reference

Full parameter specifications and response schemas:
- [defeatbeta-api-reference.md](references/defeatbeta-api-reference.md)

## Templates & Examples

Detailed workflow templates for common analysis tasks:
- [analysis-templates.md](references/analysis-templates.md)