---
name: defeatbeta-earnings-analysis
description: Create professional equity research earnings update reports (8-12 pages, 3,000-5,000 words) analyzing quarterly results for companies already under coverage. Fast-turnaround format focusing on beat/miss analysis, key metrics, updated estimates, and revised thesis. Includes 1-3 summary tables and 8-12 charts. Use when user requests "earnings update", "quarterly update", "earnings analysis", "Q1/Q2/Q3/Q4 results", or post-earnings report.
argument-hint: <TICKER> <FISCAL_QUARTER>
compatibility: Requires (1) defeatbeta MCP server (Tier 1 data — see Section 5), (2) a DOCX-creation skill such as Anthropic's "Office Document Creator" or any equivalent that exposes a `create_docx`-style interface, (3) Python environment with matplotlib, pandas, and seaborn for the 8-12 embedded charts, (4) web search for Tier 2 fallback rows and all Tier 3 sources (consensus, analyst targets, operating metrics, news).
---

# Equity Research Earnings Update

Create professional **EARNINGS UPDATE REPORTS** analyzing quarterly results for companies already under coverage, following institutional standards (JPMorgan, Goldman Sachs, Morgan Stanley format).

**Key Characteristics:**
- **Length**: 8-12 pages
- **Word Count**: 3,000-5,000 words
- **Tables**: 1-3 summary tables (NOT comprehensive)
- **Figures**: 8-12 charts
- **Audience**: Clients already familiar with the company
- **Focus**: What's NEW — beat/miss, updated estimates, thesis impact
- **Font**: Times New Roman throughout (unless user specifies otherwise)

## When to Use

Use when the user requests:
- "Create an earnings update for [Company] Q3 2024"
- "Analyze [Company]'s quarterly results"
- "Post-earnings report for [Company]"
- "Q1/Q2/Q3/Q4 update for [Company]"

**Do NOT use if:**
- User requests "initiation report" → Use different skill
- User requests "flash note" or "quick take" → Different format
- Company is not already covered → Need initiation first

## Critical Requirements

### 1. Language Matching
- Match the user's language for all user-facing output, including the DOCX report, delivery summary, replies, visible reasoning notes, assumptions, methodology explanations, and clarification questions
- If the user mixes languages, use the language that dominates the user's request unless the user explicitly specifies the report language
- Keep company names, tickers, financial terms, source names, accounting labels, and quoted source text in their original language when translation would reduce precision
- Do not expose hidden chain-of-thought; provide concise visible rationale, assumptions, and methodology in the user's language when useful
- If the report language differs from the source language, preserve source citations, MCP tool names, ticker symbols, and financial labels accurately

### 2. Focus
- Focus on what's NEW from this quarter — don't rehash company background
- Assume reader has seen the prior coverage (initiation report or prior earnings update on this name)

### 3. Beat/Miss Analysis
- Lead with whether company beat or missed estimates
- Quantify variances (e.g., "Revenue beat by $120M or 3%")
- Explain WHY results differed from expectations

### 4. Summary Format
- Keep tables to 1-3 (summary only, not comprehensive)
- No full P&L/Cash Flow/Balance Sheet (just key metrics)
- Assume reader has seen initiation report

### 5. Data Source Tiers ⭐⭐⭐ MANDATORY

Every data point in the report falls into exactly one of three tiers. Each tier has a fixed source policy — there is no "default to MCP, sometimes web" ambiguity.

#### Tier 1 — MCP only (strict)

Reported, authoritative financial data. **No web fallback.** If MCP returns nothing, state the data gap in the report and proceed; do **not** patch from 10-Q, press release, IR site, or news snippets.

| Content | MCP tool |
|---|---|
| Reported income statement | `get_stock_quarterly_income_statement` |
| Reported balance sheet | `get_stock_quarterly_balance_sheet` |
| Reported cash flow statement | `get_stock_quarterly_cash_flow` |
| Earnings call transcript (management commentary, Q&A) | `get_stock_earning_call_transcripts_list` then `get_stock_earning_call_transcript` |
| Stock price | `get_stock_price` |
| Market capitalization | `get_stock_market_capitalization` |
| WACC | `get_stock_wacc` |
| DCF / fair value | `get_stock_dcf_analysis` (or trigger the `defeatbeta-dcf` skill) |
| Valuation multiples | `get_stock_ttm_pe`, `get_stock_enterprise_value`, `get_stock_enterprise_to_ebitda`, `get_stock_enterprise_to_revenue`, `get_stock_ps_ratio`, `get_stock_pb_ratio`, `get_stock_peg_ratio` |
| Margins | `get_stock_quarterly_gross_margin`, `get_stock_quarterly_operating_margin`, `get_stock_quarterly_net_margin`, `get_stock_quarterly_ebitda_margin`, `get_stock_quarterly_fcf_margin` |
| YoY growth | `get_stock_quarterly_revenue_yoy_growth`, `get_stock_quarterly_ebitda_yoy_growth`, `get_stock_quarterly_diluted_eps_yoy_growth`, `get_stock_quarterly_fcf_yoy_growth`, `get_stock_quarterly_operating_income_yoy_growth`, `get_stock_quarterly_net_income_yoy_growth`, `get_stock_quarterly_ttm_diluted_eps_yoy_growth` |
| Capital efficiency | `get_stock_quarterly_roic`, `get_stock_quarterly_roa`, `get_stock_quarterly_roe`, `get_stock_quarterly_asset_turnover`, `get_stock_quarterly_equity_multiplier`, `get_stock_quarterly_debt_to_equity` |
| EPS | `get_stock_eps_and_ttm_eps` |
| Dataset date probe | `get_latest_data_update_date` |

#### Tier 2 — MCP preferred, web fallback allowed (must be labeled)

MCP is the primary source; web fallback is allowed when MCP returns nothing or coverage is incomplete. Fallback rows **must be explicitly labeled** in figures, tables, and the Sources section — never blended with MCP data.

| Content | Primary (MCP) | Fallback |
|---|---|---|
| Segment revenue | `get_quarterly_revenue_by_segment` | Company 10-Q / earnings release supplementary tables |
| Geography revenue | `get_quarterly_revenue_by_geography` | Company 10-Q / earnings release supplementary tables |
| Prior guidance | `get_stock_earning_call_transcript` (prior quarter) | Prior-quarter earnings release / 8-K |
| Industry / peer comparables | `get_industry_ttm_pe`, `get_industry_ps_ratio`, `get_industry_pb_ratio`, `get_industry_quarterly_gross_margin`, `get_industry_quarterly_ebitda_margin`, `get_industry_quarterly_net_margin`, `get_industry_quarterly_roa`, `get_industry_quarterly_roe`, `get_industry_quarterly_asset_turnover`, `get_industry_quarterly_equity_multiplier` | Bloomberg / FactSet peer screens |

#### Tier 3 — Web only (MCP does not cover)

Data MCP does not provide. Cite source name and "as of" date. No pretense of MCP coverage.

| Content | Source examples |
|---|---|
| Consensus estimates (revenue, EPS forecast) | Bloomberg, FactSet, Refinitiv, Yahoo Finance, TipRanks, Insider Monkey — **pre-earnings where possible** |
| Analyst price targets (avg / high / low / count) | Yahoo Finance, TipRanks, Insider Monkey |
| Stock reaction history (earnings-day price moves) | Web search, Yahoo Finance |
| Options-implied move / IV skew | Options data providers, web search |
| Operating metrics (DAU/MAU/ARPU, customer count, store count, units shipped, occupancy, RPO, NRR, etc.) | Company IR site, 10-Q supplementary tables, investor presentation |
| Recent news / policy catalysts | Reuters, Bloomberg, sector news outlets |

#### Where each tool's cache file lives (Call-Then-Write — Phase 1)

After Phase 1, every T1 and T2 MCP tool call has produced one cache file under `/tmp/<TICKER>_<PERIOD>/cache/`. This is the map: pick the right file to `Read` when drafting each section.

| Need this data | MCP tool called | Cache file (T1 unless noted) |
|---|---|---|
| Reported income statement | `get_stock_quarterly_income_statement` | `income_statement.json` |
| Reported balance sheet | `get_stock_quarterly_balance_sheet` | `balance_sheet.json` |
| Reported cash flow | `get_stock_quarterly_cash_flow` | `cash_flow.json` |
| Earnings call transcript (target period) | `get_stock_earning_call_transcript` | `transcript_current.txt` |
| Earnings call transcript (prior period — for prior guidance) | `get_stock_earning_call_transcript` (prior FY/Q) | `transcript_prior.txt` |
| Stock price | `get_stock_price` | `price.json` |
| Market cap | `get_stock_market_capitalization` | `market_cap.json` |
| EPS + TTM EPS | `get_stock_eps_and_ttm_eps` | `eps.json` |
| WACC | `get_stock_wacc` | `wacc.json` |
| Structured DCF + fair price | `get_stock_dcf_analysis` | `dcf_analysis.json` |
| P/E, EV/*, P/S, P/B, PEG | multiple multiple tools | `valuation_multiples.json` (one file, multiple tool returns) |
| Gross/op/net/EBITDA/FCF margins (history) | 5 margin tools | `margins.json` (one file, 5 returns) |
| Revenue/op-income/EBITDA/net-income/FCF/EPS YoY (history) | 6 growth tools | `growth.json` (one file, 6 returns) |
| ROIC, ROE, ROA, asset turnover, equity multiplier, D/E | 6 tools | `capital_efficiency.json` (one file, 6 returns) |
| Segment revenue (T2) | `get_quarterly_revenue_by_segment` | `segment.json` |
| Geography revenue (T2) | `get_quarterly_revenue_by_geography` | `geography.json` |
| Industry comparables (T2) | several `get_industry_*` tools | `industry.json` (one file, several returns) |

**Two helpful conventions for the multi-tool bundles** (`valuation_multiples`, `margins`, `growth`, `capital_efficiency`, `industry`):
- Within one bundled file, store each tool's return under a key named after the tool, e.g.
  ```json
  {
    "ttm_pe": {...},
    "ev_to_ebitda": {...},
    "ps_ratio": {...},
    "pb_ratio": {...},
    "peg_ratio": {...}
  }
  ```
- This still satisfies the verbatim rule — you concatenate raw returns under labeled keys; you don't summarize.

Tier 3 data lands in `/tmp/<TICKER>_<PERIOD>/cache/web_<topic>.txt` (web excerpts written verbatim from the search result). Phase 1's MCP fetch does **not** include Tier 3.

### 6. Citations & Source Attribution ⭐⭐⭐ MANDATORY

Every data point cites its source. The format depends on tier (see Section 5).

#### Citation formats by tier

**Tier 1 (MCP only):**
```
Source: DefeatBeta MCP get_stock_quarterly_income_statement, AAPL,
        fiscal period 2026-03-31, retrieved May 13, 2026.
```

For transcript-derived commentary, also cite speaker and paragraph number where available:
```
Source: DefeatBeta MCP get_stock_earning_call_transcript, AAPL FY2026 Q2,
        report date April 30, 2026, CFO prepared remarks, paragraph 14.
```

**Tier 2 (MCP preferred, web fallback labeled):**
- If sourced from MCP, use the Tier 1 format above.
- If sourced from web fallback, prefix with "Fallback:" and cite source name + retrieval date:
```
Fallback source: Apple Q2 FY2026 earnings release supplementary table,
                 https://investor.apple.com/..., retrieved May 13, 2026.
                 (DefeatBeta MCP get_quarterly_revenue_by_segment did not cover this period.)
```

**Tier 3 (web only):**
```
Source: Yahoo Finance analyst estimates, as of April 29, 2026 (pre-earnings close).
```
```
Source: TipRanks analyst price targets, retrieved May 13, 2026 (43 analysts, 3-month window).
```

#### General rules

- Cite the exact tool name (T1/T2) or source name + "as of" date (T3) — never a generic "Bloomberg" or "company filings"
- Do not display raw URLs for T1/T2 MCP sources; do display URLs for T2 fallback and T3 web sources
- For derived metrics that combine multiple MCP tools, cite each tool used
- For T2, never blend MCP rows and fallback rows in the same column without a fallback label

#### Sources section layout (end of report)

Group by tier so readers can immediately see what is authoritative vs. fallback vs. web:

```
SOURCES & REFERENCES

Tier 1 — DefeatBeta MCP (authoritative):
• get_stock_quarterly_income_statement, AAPL, fiscal period 2026-03-31, retrieved May 13, 2026
• get_stock_quarterly_balance_sheet, AAPL, fiscal period 2026-03-31, retrieved May 13, 2026
• get_stock_quarterly_cash_flow, AAPL, fiscal period 2026-03-31, retrieved May 13, 2026
• get_stock_earning_call_transcript, AAPL FY2026 Q2, report date April 30, 2026, retrieved May 13, 2026
• get_stock_dcf_analysis, AAPL, retrieved May 13, 2026

Tier 2 — DefeatBeta MCP + fallback (where applicable):
• get_quarterly_revenue_by_segment, AAPL, fiscal period 2026-03-31, retrieved May 13, 2026
• Fallback: AAPL Q2 FY2026 earnings press release, https://..., retrieved May 13, 2026
  (used for geographic split — MCP did not cover this period)

Tier 3 — Web (MCP does not cover):
• Yahoo Finance consensus estimates, as of April 29, 2026
• TipRanks analyst price targets, retrieved May 13, 2026 (43 analysts)
• Apple Q2 FY2026 user metrics — Apple IR site, https://..., retrieved May 13, 2026
```

#### Verification checklist
- [ ] Every figure/table has a source line whose format matches its tier
- [ ] T1 data: every citation names the exact MCP tool + fiscal period + retrieval date
- [ ] T1 data: no web URLs, no IR pages, no "10-Q said..."; if MCP didn't return it, the report says so
- [ ] T2 fallback rows are explicitly labeled "Fallback:" and kept visually separate from MCP rows
- [ ] T3 citations include source name + "as of" date (pre-earnings where applicable)
- [ ] Sources section is grouped by T1/T2/T3

### 7. Updated Estimates
- Update forward estimates based on results
- Show old vs. new estimates clearly when prior coverage is available
- Explain what changed and why

## High-Level Workflow

The earnings update process has 5 phases. Detailed procedures live in [references/workflow.md](references/workflow.md); the summary below is for orientation only.

### Phase 1: Data Collection — Call-Then-Write Pattern

**The goal of this phase is not just to retrieve data — it is to create an on-disk source of truth that the report draws from later.** Conversation context can be compressed at any time; compressed summaries paraphrase numbers. A report that cites numbers from compressed context is a report that hallucinates digits. The cache is the antidote.

For **every** Tier 1 and Tier 2 MCP tool call:

1. **Call** the MCP tool.
2. **Immediately Write the full return value verbatim** to `/tmp/<TICKER>_<PERIOD>/cache/<tool_name>.json` (or `.txt` for transcripts). No paraphrasing. No restructuring. No summarizing. No omitting fields. Byte-for-byte copy. If the return is JSON, Write the JSON as-is; if it's a dict object in your context, serialize it to JSON before Write.
3. Only after the cache file is written, move on to the next tool.

**Why verbatim matters:** the very temptation to "I already saw this data, let me just save the key fields" is what breaks traceability. Once you skip a field at Write time, no later Read can recover it. Resist the temptation. Write everything.

**Cache directory layout** (see Section 5 below for the full file map):

```
/tmp/<TICKER>_<PERIOD>/cache/
  ├── income_statement.json
  ├── balance_sheet.json
  ├── cash_flow.json
  ├── transcript_current.txt
  ├── transcript_prior.txt
  ├── price.json
  ├── market_cap.json
  ├── eps.json
  ├── wacc.json
  ├── dcf_analysis.json
  ├── valuation_multiples.json    (P/E, EV/EBITDA, EV/Rev, P/S, P/B, PEG bundled)
  ├── margins.json                 (5 margins bundled)
  ├── growth.json                  (6 YoY growth metrics bundled)
  ├── capital_efficiency.json      (ROIC, ROE, ROA, asset turnover, etc. bundled)
  ├── segment.json
  ├── geography.json
  └── industry.json
```

**Choose `<PERIOD>` after Step 0 below** so the directory path is concrete (e.g. `/tmp/AMD_FY2025_Q1/cache/`).

#### Step 0: pick the period (very small calls, no caching needed)

1. Call `get_latest_data_update_date` → write down the dataset date.
2. Call `get_stock_earning_call_transcripts_list(symbol)` → pick the target fiscal period (latest by default, or the user-specified `fiscal_year` + `fiscal_quarter`).

Both calls return tiny payloads — they don't need cache files.

#### Tier 3 data

Tier 3 (consensus, analyst PT, operating metrics, news) comes from web search at report-writing time. **Apply the same Call-Then-Write discipline to web results**: when you fetch a consensus number or a stock-reaction stat, Write the relevant excerpt to `/tmp/<TICKER>_<PERIOD>/cache/web_<topic>.txt` so it's traceable.

#### When MCP returns nothing for a T1 tool

State the gap in the report; do **not** patch from web. T1 has no fallback by design (see Section 5).

#### Reading the cache when drafting the report

**Before citing any number** in the report, `Read` the corresponding cache file. Do **not** rely on numbers you remember from earlier tool calls — context compression can have altered them. The cache file is the only authoritative source once Phase 1 is complete.

If a cache file is large (e.g. `transcript_current.txt` is 50K+ chars), use `Read` with `offset` + `limit` to fetch only the relevant section rather than the whole file.

### Phase 2: Analysis
- Beat/miss analysis for each key metric
- Segment/geographic/product breakdown
- Margin and guidance analysis
- Update financial model and estimates

### Phase 3: Chart Generation
Create 8-12 charts focusing on quarterly trends and what's new:
- Quarterly revenue progression
- Quarterly EPS progression
- Quarterly margin trends
- Revenue by segment/geography
- Key operating metrics
- Beat/miss summary
- Estimate revisions
- Valuation charts

**See [references/workflow.md](references/workflow.md)** for chart specifications.

### Phase 4: Report Creation
Create the 8-12 page DOCX report.

**See [references/report-structure.md](references/report-structure.md)** for complete page-by-page templates and formatting requirements.

**High-level structure:**
- Page 1: Earnings summary with rating and price target
- Pages 2-3: Detailed results analysis
- Pages 4-5: Key metrics & guidance
- Pages 6-7: Updated investment thesis
- Pages 8-10: Valuation & estimates
- Pages 11-12: Appendix (optional)

### Phase 5: Quality Check & Delivery
Verify content, formatting, accuracy, and tier-correct citations before delivery. See [references/best-practices.md](references/best-practices.md) for the full checklist (single source of truth — do not duplicate verification logic elsewhere).

## Output Specification

**Primary Deliverable**: DOCX report (8-12 pages)
**File Name**: `[Company]_Q[Quarter]_[Year]_Earnings_Update.docx`
**Example**: `Nike_Q2_FY24_Earnings_Update.docx`

**Contents:**
- Page 1: Summary with rating, price target, key takeaways
- Pages 2-3: Detailed results analysis
- Pages 4-5: Key metrics and guidance
- Pages 6-7: Updated thesis assessment
- Pages 8-10: Valuation and estimates
- Pages 11-12: Appendix (optional)
- 8-12 embedded charts
- 1-3 summary tables
- Complete sources section with DefeatBeta MCP tool attribution

**Optional Deliverable**: XLS model update (optional for earnings updates)

## Key Differences from Initiation Report

| Aspect | Earnings Update | Initiation Report |
|--------|----------------|-------------------|
| **Length** | 8-12 pages | 30-50 pages |
| **Words** | 3,000-5,000 | 10,000-15,000 |
| **Tables** | 1-3 summary | 12-20 comprehensive |
| **Figures** | 8-12 | 25-35 |
| **Turnaround** | 1-2 days | 3-6 weeks |
| **Scope** | Quarterly results | Complete company |
| **Focus** | What's NEW | Everything |
| **Company Background** | Brief mention | 6-10 pages |
| **XLS Model** | Optional | Required |

## Resources

### references/workflow.md
Detailed Phase 1-5 instructions with step-by-step procedures for data collection, analysis, chart generation, and report creation.

### references/report-structure.md
Complete page-by-page templates, table formats, and formatting requirements for the DOCX report.

### references/best-practices.md
Examples of good/bad headlines, tips for success, common mistakes to avoid, and comprehensive quality checklist.

## Dependencies

**Required:**
- **DefeatBeta MCP server** — supplies all Tier 1 data (reported financials, transcripts, valuation, margins, market data). The skill cannot start without it.
- **A DOCX-creation skill** — Anthropic's "Office Document Creator" works out of the box. Any skill that can create a .docx with text, tables, and embedded images works. If none is available, fall back to producing a Markdown report and tell the user the DOCX skill is missing.
- **Python with matplotlib, pandas, seaborn** — for generating the 8-12 charts. The chart-generation phase requires a working Python interpreter accessible via the runtime (Code Interpreter, Bash + python, Jupyter, etc.). If unavailable, skip chart generation, explain the gap to the user, and ship a text-only report.
- **Web search** — Tier 2 fallback rows and all Tier 3 sources (consensus, analyst targets, operating metrics, news). If web search is disabled, every T3 row must be flagged as "unavailable in this environment."

**Optional:**
- **`defeatbeta-dcf` skill** — produces an editable DCF Excel; reference it from Step 10 when the user wants a working DCF spreadsheet alongside the earnings report.
- **Spreadsheets / XLS skill** — for updating an existing full financial model (not required; see workflow.md Step 14).
