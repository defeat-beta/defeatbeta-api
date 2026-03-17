---
name: defeatbeta-analyst
description: "Professional financial analysis using 60+ market data APIs. Use for: company fundamentals (revenue, margins, EPS, balance sheet), valuation (P/E, P/B, P/S, PEG, DCF, intrinsic value), profitability (ROE, ROA, ROIC), growth trends (YoY revenue/earnings/FCF), earnings transcripts (key data, changes, guidance), industry benchmarking, segment/geography revenue breakdown, business model analysis, competitive landscape, risk analysis, investment thesis, bull/bear scenarios. Trigger on: stock tickers, company names, financial metrics, or any investment research request. DO NOT trigger for: general economics, non-public companies, crypto/commodities with no equity ticker."
argument-hint: <TICKER> [analysis-type]
compatibility: Requires defeatbeta MCP server
---

# Financial Analyst

Professional-grade financial analysis using historical market data and comprehensive financial metrics from the [defeatbeta dataset](https://huggingface.co/datasets/defeatbeta/yahoo-finance-data).

## Defaults

Unless the user specifies otherwise:

- **Always call `get_latest_data_update_date` first** — this is "today" for all relative time queries
- **Default analysis**: When given only a ticker (e.g., `/defeatbeta-analyst AAPL`), run **Template 1: Quick Investment Screening**
- **ROIC and Equity Multiplier**: Not applicable to banks/financial institutions — check `sector` in profile first
- **Date format**: "YYYY-MM-DD"
- **Data limits**: Price/valuation APIs return max 1000 rows — use date ranges for large datasets

## Template Selection

Choose the template that best matches the user's request. Read [analysis-templates.md](./references/analysis-templates.md) for the full workflow of any template.

| User request                                  | Template                                           |
|-----------------------------------------------|----------------------------------------------------|
| Quick check / "should I look at this stock?"  | T1: Quick Investment Screening                     |
| Full company deep-dive                        | T2: Full Fundamental Analysis                      |
| Overvalued / undervalued / P/E / P/B / DCF    | T3: Valuation-Focused or T10: DCF Valuation        |
| Revenue growth / earnings quality / ROIC      | T4: Growth Quality Assessment                      |
| ROE decomposition / DuPont                    | T5: DuPont Analysis                                |
| Margin trends / vs peers                      | T6: Margin Analysis & Peer Comparison              |
| Accruals / FCF quality / working capital      | T7: Earnings Quality Assessment                    |
| Industry positioning                          | T8: Industry Positioning Analysis                  |
| Latest earnings release numbers               | T9: Quarterly Earnings Analysis                    |
| "What did management report this quarter?"    | T11: Extract Key Financial Data from Earnings Call |
| "What changed vs last quarter/year?"          | T12: Financial Metric Changes from Earnings Call   |
| "What is management's guidance/outlook?"      | T13: Financial Metric Forecasts from Earnings Call |
| "What does this company do?" / business model | T14: Business Understanding                        |
| Revenue segments / geography breakdown        | T15: Revenue Breakdown                             |
| Industry trends / tailwinds / headwinds       | T16: Industry Context                              |
| Competitors / moat / pricing power            | T17: Competitive Landscape                         |
| Balance sheet strength / debt / FCF quality   | T18: Financial Quality                             |
| Risks / downside / what could go wrong        | T19: Risks and Downside                            |
| Management track record / capital allocation  | T20: Management and Execution                      |
| Bull case / bear case / scenarios             | T21: Bull and Bear Scenarios                       |
| How to value / valuation assumptions          | T22: Valuation Framework                           |
| Long-term thesis / why invest / must go right | T23: Long-Term Investment Thesis                   |

## API Gotchas

**REQUIRED**: Before calling any API, read the relevant section in [defeatbeta-api-reference.md](./references/defeatbeta-api-reference.md) to confirm the correct parameters and response schema.

1. **Fiscal periods**: Earnings transcripts use fiscal periods (may differ from calendar) — specify both `fiscal_year` and `fiscal_quarter`
2. **SEC filing access**: Must use `sec_user_agent` field value as User-Agent header when accessing SEC URLs (SEC blocks without it)

## Rendering Financial Statements

When displaying results from `get_stock_*_income_statement`, `get_stock_*_balance_sheet`, or `get_stock_*_cash_flow`, you MUST follow these rules. The response contains a `statement` array where each row has `label`, `indent`, `is_section`, and `values` fields.

**Rules:**

1. **Preserve row order** — never reorder, skip, or merge rows
2. **Indent** — prefix each label with `indent × 2` spaces (`indent=0` → no prefix, `indent=1` → 2 spaces, `indent=2` → 4 spaces, etc.)
3. **is_section=true** — render the label in **bold**; this row is a section header and the rows immediately below it (with `indent = this.indent + 1`) are its children
4. **is_section=false** — render the label in normal weight
5. **values[i]** corresponds to `periods[i]`; `null` means data not available
6. **Do NOT add calculated rows** (e.g. margin %) that are not present in the data

**Example — given these rows:**

| label             | indent | is_section |
|-------------------|--------|------------|
| Total Revenue     | 0      | true       |
| Operating Revenue | 1      | false      |
| Cost of Revenue   | 0      | false      |
| Operating Expense | 0      | true       |
| SG&A              | 1      | false      |
| R&D               | 1      | false      |

**Correct rendered output:**

| Item                          | 2025Q4 | 2025Q3 |
|-------------------------------|--------|--------|
| **Total Revenue**             | 10,270 | 9,246  |
| &nbsp;&nbsp;Operating Revenue | 10,270 | 9,246  |
| Cost of Revenue               | 4,693  | 4,466  |
| **Operating Expense**         | 3,825  | 3,510  |
| &nbsp;&nbsp;SG&A              | 1,198  | 1,069  |
| &nbsp;&nbsp;R&D               | 2,330  | 2,139  |

## Reference Documentation

**Detailed step-by-step workflows (T1–T23)** → [analysis-templates.md](./references/analysis-templates.md)

**API parameters, response schemas, examples (60+ APIs)** → [defeatbeta-api-reference.md](./references/defeatbeta-api-reference.md)
