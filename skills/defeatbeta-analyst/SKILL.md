---
name: defeatbeta-analyst
description: "Comprehensive financial analysis using 60+ data endpoints. Analyze company fundamentals, financial statements, valuation metrics, profitability ratios, growth trends, and industry comparisons. Use for: (1) fundamental analysis and DCF modeling, (2) financial statement analysis, (3) valuation and ratio analysis, (4) growth and profitability assessment, (5) industry benchmarking, or any deep financial research tasks."
---

# Financial Analyst

Professional-grade financial analysis using historical market data and comprehensive financial metrics from the [defeatbeta dataset](https://huggingface.co/datasets/defeatbeta/yahoo-finance-data).

## Core Capabilities

- **Market Data**: S&P 500 returns, Treasury yields, stock prices, market cap, beta
- **Company Intelligence**: Profiles, executives, SEC filings, earnings transcripts, news
- **Financial Statements**: Income statement, balance sheet, cash flow (quarterly & annual)
- **Valuation Metrics**: P/E, P/S, P/B, PEG ratios, market cap, WACC
- **Profitability Analysis**: Margins (gross, operating, net, EBITDA, FCF), ROE, ROA, ROIC
- **Growth Analysis**: YoY growth for revenue, earnings, EBITDA, FCF, EPS
- **DCF Modeling**: Automated discounted cash flow valuation with WACC, growth projections, fair value
- **Segment Analysis**: Revenue by business segment and geography
- **Industry Benchmarking**: Compare against industry averages for all metrics
- **DuPont Analysis**: Equity multiplier, asset turnover decomposition

## Dataset Reference Date

**CRITICAL**: Always call `get_latest_data_update_date` at the start of analysis to determine the data cutoff date. This is the "today" for all relative time queries (e.g., "last 10 days", "past quarter", "YTD").

## Available APIs

60+ financial data APIs covering:
- Market & Macro Data (S&P 500, Treasury yields, market data)
- Company Information (profile, officers, SEC filings, earnings calls, news)
- Price & Market Data (stock prices, market cap, P/E, WACC)
- Financial Statements (income statement, balance sheet, cash flow - quarterly & annual)
- Profitability Metrics (margins, ROE, ROA, ROIC)
- Valuation Ratios (P/E, P/S, P/B, PEG)
- Growth Metrics (YoY growth for revenue, earnings, FCF, EPS)
- Industry Benchmarking (compare vs industry averages)
- Segment Analysis (revenue by segment/geography)

**For complete API list with parameters and schemas**, see [defeatbeta-api-reference.md](references/defeatbeta-api-reference.md)

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
11. **DCF Valuation** - Calculate intrinsic value using discounted cash flow (WACC, growth projections, terminal value)

## Using the APIs

**Critical requirements:**
1. **Always call `get_latest_data_update_date` first** - This is the "today" for all relative time queries
2. **Data limits**: Stock price/valuation APIs return max 1000 rows - use date ranges for larger datasets
3. **ROIC and Equity Multiplier not applicable to banks** - Check `sector` in profile to identify financial institutions
4. **Fiscal periods**: Earnings transcripts use fiscal periods (may differ from calendar) - specify both `fiscal_year` and `fiscal_quarter`
5. **SEC filing access**: Must use `sec_user_agent` field value as User-Agent header when accessing SEC URLs (SEC blocks without it)

**Date format**: "YYYY-MM-DD" (e.g., "2020-01-01")

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

## Templates & Examples

Detailed workflow templates for common analysis tasks:
- [analysis-templates.md](references/analysis-templates.md)