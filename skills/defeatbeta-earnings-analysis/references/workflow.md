# Detailed Workflow for Earnings Updates

Detailed step-by-step instructions for each phase. See SKILL.md Section 5 for the Tier 1/2/3 data source policy that governs every retrieval below.

## Phase 1: Earnings Data Collection

### Step 1: Identify the Target Earnings Period

Always anchor the target period to DefeatBeta MCP metadata, never to training-data assumptions.

**Step 1a: Establish the Data Reference Date**

- Call `get_latest_data_update_date` and write down `latest_data_date`. This is the data availability anchor — not the model's training cutoff.

**Step 1b: Identify the Target Period**

- Call `get_stock_earning_call_transcripts_list(symbol)`
- If the user wants the latest update: pick the most recent transcript record by fiscal year/quarter and report date
- If the user specified a quarter: select the matching `fiscal_year` and `fiscal_quarter`
- Treat transcript metadata as the authoritative fiscal-period selector; do not infer the quarter from today's date

**Step 1c: Verify the Period**

- Confirm the transcript's `fiscal_year`, `fiscal_quarter`, and `report_date` match the user's request (or are the latest if no period was specified)
- Confirm the selected period appears in the `periods` array returned by each quarterly statement tool you call in Step 2
- If any of these checks fail, re-call the transcripts list and statement tools before continuing

**Step 1d: Understand Company's Fiscal Calendar**

After identifying the target period from MCP transcript metadata, understand the company's fiscal year to interpret it correctly:

**Common fiscal year patterns:**
- **Calendar year (CY)**: Q1=Jan-Mar, Q2=Apr-Jun, Q3=Jul-Sep, Q4=Oct-Dec
- **Nike fiscal**: Q1=Jun-Aug, Q2=Sep-Nov, Q3=Dec-Feb, Q4=Mar-May (May fiscal year-end)
- **Apple fiscal**: Q1=Oct-Dec, Q2=Jan-Mar, Q3=Apr-Jun, Q4=Jul-Sep (September fiscal year-end)
- **Walmart fiscal**: Q1=Feb-Apr, Q2=May-Jul, Q3=Aug-Oct, Q4=Nov-Jan (January fiscal year-end)

Use the fiscal year and fiscal quarter returned by DefeatBeta MCP as authoritative. Do not infer fiscal periods from calendar dates alone.

**Step 1e: Disambiguate Date Fields**

Three date concepts often get confused — keep them straight:
- `fiscal_year` / `fiscal_quarter` — follow the company's fiscal calendar (not the calendar year)
- Statement `periods` — fiscal-period end dates returned by the quarterly statement tools
- Transcript `report_date` — the earnings call/release date, distinct from the period end

User phrasings like "Q1 2024" / "1Q24" / "First Quarter 2024" / "Q1 FY24" all refer to the same `fiscal_year, fiscal_quarter` tuple from MCP — let the MCP metadata be authoritative.

### Step 2: Gather Earnings Data

After confirming the target fiscal period from DefeatBeta MCP, collect data in the order **T1 → T2 → T3** (see SKILL.md Section 5 for the full tier table). Each tier has a different source policy; do not blend them.

#### Tier 1 — MCP only (no web fallback)

Call each tool below and verify the selected fiscal period appears in the returned data. If a tool returns nothing for the target period, **state the gap in the report and proceed** — do not patch from 10-Q, press releases, IR pages, or news.

**Reported financial statements:**
- `get_stock_quarterly_income_statement(symbol)` — revenue, gross profit, operating income, net income, EPS, share count, EBIT, EBITDA
- `get_stock_quarterly_balance_sheet(symbol)` — assets, liabilities, equity, cash, debt, working capital, invested capital
- `get_stock_quarterly_cash_flow(symbol)` — operating cash flow, capex, free cash flow, buybacks, dividends, debt issuance/repayment

**Earnings call transcript** (already retrieved in Step 1 — use the same `fiscal_year`, `fiscal_quarter` to keep statement/transcript periods aligned):
- `get_stock_earning_call_transcript(symbol, fiscal_year, fiscal_quarter)`
- Extract management guidance, outlook, demand commentary, margin commentary, capital allocation comments, Q&A themes, management tone, and forward-looking statements
- **Period-alignment check**: transcript `fiscal_year` / `fiscal_quarter` MUST match the selected statement period. If they diverge, you have the wrong transcript — re-check the list.

**Market data:**
- `get_stock_price(symbol)` — current price, used in Page 1 header
- `get_stock_market_capitalization(symbol)` — market cap
- `get_stock_wacc(symbol)` — WACC, used in DCF valuation
- `get_stock_eps_and_ttm_eps(symbol)` — reported EPS + TTM EPS

**Valuation multiples** (call those the report cites):
- `get_stock_ttm_pe`, `get_stock_enterprise_value`, `get_stock_enterprise_to_ebitda`, `get_stock_enterprise_to_revenue`, `get_stock_ps_ratio`, `get_stock_pb_ratio`, `get_stock_peg_ratio`
- `get_stock_dcf_analysis` — returns the structured DCF with fair price; in most cases use this as the DCF anchor rather than re-deriving (the `defeatbeta-dcf` skill is the editable spreadsheet counterpart of the same calculation)

**Growth / margins / capital efficiency:**
- Margins: `get_stock_quarterly_gross_margin`, `get_stock_quarterly_operating_margin`, `get_stock_quarterly_net_margin`, `get_stock_quarterly_ebitda_margin`, `get_stock_quarterly_fcf_margin`
- YoY growth: `get_stock_quarterly_revenue_yoy_growth`, `get_stock_quarterly_ebitda_yoy_growth`, `get_stock_quarterly_diluted_eps_yoy_growth`, `get_stock_quarterly_fcf_yoy_growth`, `get_stock_quarterly_operating_income_yoy_growth`, `get_stock_quarterly_net_income_yoy_growth`
- Capital efficiency: `get_stock_quarterly_roic`, `get_stock_quarterly_roa`, `get_stock_quarterly_roe`, `get_stock_quarterly_asset_turnover`, `get_stock_quarterly_equity_multiplier`, `get_stock_quarterly_debt_to_equity`

**Period comparisons** (for QoQ / YoY tables):
- Prior quarter and prior-year same-quarter values are returned in the same MCP statement responses (multiple `periods`) — no extra call needed

#### Tier 2 — MCP preferred, web fallback allowed (must be labeled)

Try MCP first. If MCP doesn't return the data for the target period, web fallback is allowed but **must be labeled with "Fallback:"** in the figure/table source line.

**Segment revenue:**
- Primary: `get_quarterly_revenue_by_segment(symbol)`
- Fallback (if MCP returns nothing or coverage is partial): company 10-Q / earnings press release supplementary tables — label as fallback

**Geography revenue:**
- Primary: `get_quarterly_revenue_by_geography(symbol)`
- Fallback: same as segment — 10-Q / earnings release — label as fallback

**Prior guidance** (for guidance-change analysis):
- Primary: prior-quarter `get_stock_earning_call_transcript(symbol, prior_fiscal_year, prior_fiscal_quarter)`
- Fallback (if prior transcript unavailable): prior-quarter press release / 8-K — label as fallback

**Industry / peer comparables:**
- Primary: `get_industry_ttm_pe`, `get_industry_ps_ratio`, `get_industry_pb_ratio`, `get_industry_quarterly_gross_margin`, `get_industry_quarterly_ebitda_margin`, `get_industry_quarterly_net_margin`, `get_industry_quarterly_roa`, `get_industry_quarterly_roe`, `get_industry_quarterly_asset_turnover`, `get_industry_quarterly_equity_multiplier`
- Fallback: Bloomberg / FactSet peer screens — label as fallback

#### Tier 3 — Web only (MCP does not cover, go straight to web)

Do not waste calls hunting for MCP coverage here. Go to web and cite source + "as of" date.

**Consensus estimates** (revenue, EPS, segment estimates) — **pre-earnings where possible**:
- Bloomberg, FactSet, Refinitiv, Yahoo Finance, TipRanks, Insider Monkey, etc.
- Required for beat/miss analysis; cite with "as of [pre-earnings date]"

**Analyst price targets** (avg / high / low / count):
- Yahoo Finance, TipRanks, Insider Monkey, MarketBeat

**Operating metrics** (DAU, MAU, ARPU, customer count, store count, units shipped, RPO, NRR, occupancy, etc.):
- Company IR site, 10-Q supplementary tables, investor presentations
- MCP does not provide business-level KPIs; this is web by design

**Stock reaction history** (earnings-day price moves):
- Web search, Yahoo Finance historical reactions

**Options-implied move / IV skew**:
- Options data providers, web search

**Recent news / policy / catalysts**:
- Reuters, Bloomberg, sector outlets

#### Prior estimates (optional reference data)

- **If this company was previously covered** (by the user, by this skill in a prior quarter, or by a sell-side firm whose research is on the web), retrieve the prior estimates, prior rating, and prior price target for the "Old vs. New" comparison
- Sources: user-provided previous model / report, prior `[Company]_Q[X]_[Year]_Earnings_Update.docx` if available, web search for "[firm] previous [Company] coverage", or a prior consensus snapshot
- If prior estimates cannot be found, the report still proceeds — beat/miss is computed against consensus only, and the "Old" columns can be omitted or marked "N/A". Do not fabricate prior numbers.

**Verification before Step 3:**

Confirm before continuing:
- The fiscal period appears in the `periods` array of every T1 statement tool you called (income / balance / cash flow)
- The transcript's `fiscal_year` / `fiscal_quarter` match the statement period
- Any T2 fallback rows are labeled (segment/geography/industry/prior guidance)
- Any T1 gaps are noted for the report — not patched from web

If a check fails, re-call the failing tool or document the gap. Do not proceed with mismatched periods.

### Step 3: Extract Key Metrics

Create a structured summary:

```
REPORTED RESULTS vs. ESTIMATES:
─────────────────────────────────────────────────
                    Reported    Our Est    Consensus    Beat/(Miss)
Revenue             $X,XXX      $X,XXX     $X,XXX       $XX (X%)
Gross Margin        XX.X%       XX.X%      XX.X%        XXbps
EBITDA              $XXX        $XXX       $XXX         $XX (X%)
Operating Profit    $XXX        $XXX       $XXX         $XX (X%)
EPS (Adjusted)      $X.XX       $X.XX      $X.XX        $X.XX
EPS (GAAP)          $X.XX       $X.XX      $X.XX        $X.XX

KEY BUSINESS METRICS:
─────────────────────────────────────────────────
[Metric 1]          XXX         XXX        XXX          +X% YoY
[Metric 2]          XXX         XXX        XXX          +X% YoY
[Metric 3]          XXX         XXX        XXX          +X% YoY
```

### Step 4: Identify Key Themes from Call

Use the earnings call transcript retrieved from the defeatbeta MCP transcript tools and note:
- Management's tone (confident, cautious, defensive?)
- Key topics emphasized (product launches, geographic trends, competition)
- Questions from analysts (what are investors concerned about?)
- Guidance provided (raised, lowered, maintained, introduced?)
- Any surprises or unexpected commentary

## Phase 2: Analysis

### Step 5: Beat/Miss Analysis

For EACH key metric that beat or missed, explain:

**If BEAT:**
- What drove the outperformance?
- Was it one-time or sustainable?
- Did management guide higher going forward?
- How does this impact our thesis?

**If MISS:**
- What went wrong?
- Was it company-specific or industry-wide?
- Is management taking corrective action?
- How does this impact our thesis?

**Example Format:**
```
■ **Revenue Beat by 3% Driven by Strong DTC Performance**

Revenue of $13.5B exceeded our estimate of $13.1B by $400M (3%) and consensus
of $13.2B by $300M (2%). The outperformance was driven primarily by Direct-to-
Consumer channels, which grew 18% YoY (vs. our 12% estimate), offsetting
weaker-than-expected wholesale (-5% vs. flat estimate). Management cited strong
digital demand and successful product launches (Pegasus 40 running shoe, new
Jordan colorways) as key drivers. DTC now represents 42% of total revenue vs.
38% a year ago, demonstrating successful channel shift strategy.
```

### Step 6: Segment/Geographic/Product Analysis

Analyze performance by:
- Business segment (if multi-segment company)
- Geography (North America, Europe, China, etc.)
- Product category
- Channel (retail, wholesale, e-commerce)

Identify:
- What outperformed expectations?
- What underperformed?
- Trends vs. prior quarters
- Management commentary on outlook for each area

### Step 7: Margin Analysis

Analyze profitability:
- Gross margin: up or down? why?
- Operating margin: up or down? why?
- Key drivers (pricing, mix, costs, leverage)
- Outlook going forward

### Step 8: Guidance Analysis

If company provided guidance:
- Compare new guidance to prior guidance
- Compare to internal estimates and Street estimates
- Assess credibility (does company have track record of sandbagging? beating?)
- Identify key assumptions behind guidance

If company did NOT provide guidance:
- Note this explicitly
- Provide independent outlook based on results and commentary

### Step 9: Update Financial Model

Update estimates for:
- Current year (remaining quarters)
- Next year
- Potentially year after

**Show clearly:**
```
UPDATED ESTIMATES:
─────────────────────────────────────────────────
                        Old Est     New Est     Change      Reason
FY2024E Revenue         $XX.XB      $XX.XB      +X.X%      [Brief reason]
FY2024E EBITDA          $X.XB       $X.XB       +X.X%      [Brief reason]
FY2024E EPS             $X.XX       $X.XX       +X.X%      [Brief reason]

FY2025E Revenue         $XX.XB      $XX.XB      +X.X%      [Brief reason]
FY2025E EBITDA          $X.XB       $X.XB       +X.X%      [Brief reason]
FY2025E EPS             $X.XX       $X.XX       +X.X%      [Brief reason]
```

### Step 10: Update Valuation & Price Target

Based on updated estimates:
- **DCF anchor**: call `get_stock_dcf_analysis(symbol)` (Tier 1) to get the structured DCF and fair price. This is the recommended starting point — its inputs (WACC, growth, margins, cash, shares) are all MCP-sourced and consistent with the rest of the report. If the user needs an editable spreadsheet, invoke the `defeatbeta-dcf` skill to produce one; do not re-derive a DCF from scratch unless you have a specific reason to override an MCP-derived input.
- **Multiples cross-check**: compare to `get_stock_ttm_pe`, `get_stock_enterprise_to_ebitda`, `get_stock_ps_ratio` and the corresponding `get_industry_*` peer averages (Tier 2 — peer mappings may need web fallback)
- **Sanity-check vs. analyst targets**: Tier 3 web — pull average / range of analyst price targets to position your PT vs. Street

**Price Target Decision:**
- If estimates changed significantly (>5%) → Usually change price target
- If estimates changed marginally (<5%) → May maintain price target
- If thesis strengthened/weakened → May change even without estimate change

### Step 11: Assess Rating Impact

Decide whether to change rating relative to the prior rating.

- If results significantly better than expected + guidance raised → Consider upgrade
- If results significantly worse + guidance cut → Consider downgrade
- If inline or mixed → Usually maintain rating

**Consider:**
- Stock reaction (up/down/flat?)
- Valuation (expensive/cheap relative to new estimates?)
- Risk/reward (asymmetry shifted?)

Output: `Rating: [MAINTAIN / RAISE TO / LOWER TO] [OUTPERFORM / EQUAL-WEIGHT / UNDERPERFORM]`

## Phase 3: Chart Generation

### Step 12: Generate 8-12 Charts

Create charts focusing on QUARTERLY TRENDS and WHAT'S NEW.

**REQUIRED CHARTS (8-12 total):**

1. **Quarterly Revenue Progression** (Bar chart)
   - Last 8-12 quarters
   - Show beat/miss vs. estimates each quarter
   - Highlight current quarter

2. **Quarterly EPS Progression** (Bar chart)
   - Last 8-12 quarters
   - Show beat/miss vs. estimates
   - Adjusted and GAAP

3. **Quarterly Margin Trend** (Line chart)
   - Gross margin, EBIT margin, net margin
   - Last 8-12 quarters
   - Show trajectory

4. **Revenue by Segment/Geography** (Stacked bar OR table)
   - Current quarter vs. YoY
   - Growth rates by segment

5. **Key Operating Metrics** (Multi-line chart)
   - Customer count, ARPU, units sold, etc. (whatever is relevant)
   - Last 8-12 quarters

6. **Beat/Miss Summary** (Waterfall or table)
   - Show components of beat/miss
   - What drove variance from estimates

7. **Estimate Revision Chart** (Before/after comparison)
   - Old FY estimates vs. new FY estimates
   - Bar chart showing change

8. **Valuation Chart** (P/E or EV/EBITDA multiple)
   - Historical multiple range
   - Current multiple
   - Fair value multiple

**OPTIONAL CHARTS (if space allows):**
- Peer comparison (if peers have reported)
- Guidance vs. Street comparison
- Cash flow metrics
- Balance sheet highlights (if notable)

**Chart Style Guidelines:**
- Focus on TRENDS (quarterly progression)
- Highlight CHANGES (beat/miss, estimate revisions)
- Keep simple and clear (this is a fast-turnaround report)

## Phase 4: Report Creation

### Step 13: Create DOCX Report

Use documents skill to create 8-12 page report.

See [report-structure.md](report-structure.md) for complete page-by-page templates and formatting requirements.

**Key Steps:**
1. Create Page 1 with earnings summary and quick takeaways
2. Add detailed results analysis (Pages 2-3)
3. Include key metrics and guidance (Pages 4-5)
4. Update investment thesis (Pages 6-7)
5. Provide valuation and estimates (Pages 8-10)
6. Add appendix if needed (Pages 11-12)
7. Embed all 8-12 charts throughout
8. Add 1-3 summary tables
9. Include complete sources section with DefeatBeta MCP tool attribution

### Step 14: Optional - Update XLS Model

If a full financial model exists for this company (from initiation), update it with:
- Actual Q[X] results
- Revised estimates for future quarters
- Updated valuation

**Note**: For earnings updates, a full XLS file is OPTIONAL (not required like in initiation reports). The DOCX report is the primary deliverable.

If creating XLS, include:
- Quarterly model tab
- Updated annual projections
- Revised DCF
- Updated comps analysis

## Phase 5: Quality Check & Delivery

### Step 15: Quality Checklist

Run the full checklist from [best-practices.md](best-practices.md) before delivery — it covers content, format, tier-correct citations, and accuracy. Do not duplicate the checklist here; best-practices.md is the single source of truth.

### Step 16: Deliver Report

Deliverables:
1. DOCX report — `[Company]_Q[X]_[Year]_Earnings_Update.docx`
2. PNG/JPG chart files (for reference)
3. Optional XLS — updated financial model if one is being maintained

Use the summary template in [best-practices.md → Summary Delivery Format](best-practices.md#summary-delivery-format) when reporting back to the user.
