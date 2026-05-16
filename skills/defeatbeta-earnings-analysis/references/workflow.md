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

### Step 2: Gather Earnings Data — Call-Then-Write

Each MCP tool call is followed **immediately** by a `Write` of the verbatim return value to a cache file under `./<TICKER>_<PERIOD>/cache/`. The point is not to save tokens — context can compress, that's fine. The point is to create an **on-disk source of truth** the report can later `Read` precisely, instead of citing numbers from a possibly compressed conversation history.

#### Verbatim discipline (non-negotiable)

When Writing a tool's return value to its cache file:
- **Do not** paraphrase, restructure, or summarize
- **Do not** drop fields that look "unimportant" — you don't know what the report will cite later
- **Do not** combine multiple tools' returns into one bag of fields; use the cache-file map below or, for bundled files, store each tool's return under a labeled key (see SKILL.md Section 5)
- If the return is a Python dict in your context, serialize it to JSON before Write

The cache file is the report's source of truth. A field skipped at Write time is lost forever.

#### Setup

After Step 1 you know the target fiscal year/quarter and (optionally) the prior period. Create the cache directory:

```bash
mkdir -p ./<TICKER>_FY<YEAR>_Q<QUARTER>/cache
```

Example: `mkdir -p ./AMD_FY2025_Q1/cache`.

The cache lives **under the current working directory**, not under `/tmp`. Same convention as the `defeatbeta-dcf` skill. If cwd is not writable, fall back to `mktemp -d` and update path references in the rest of this section.

#### Tier 1 — call each tool, then Write its return verbatim

| MCP tool | Cache file (under `./<TICKER>_<PERIOD>/cache/`) |
|---|---|
| `get_stock_quarterly_income_statement(symbol)` | `income_statement.json` |
| `get_stock_quarterly_balance_sheet(symbol)` | `balance_sheet.json` |
| `get_stock_quarterly_cash_flow(symbol)` | `cash_flow.json` |
| `get_stock_earning_call_transcript(symbol, FY, Q)` for target period | `transcript_current.txt` |
| `get_stock_earning_call_transcript(symbol, prior FY, prior Q)` | `transcript_prior.txt` |
| `get_stock_price(symbol)` | `price.json` |
| `get_stock_market_capitalization(symbol)` | `market_cap.json` |
| `get_stock_eps_and_ttm_eps(symbol)` | `eps.json` |
| `get_stock_wacc(symbol)` | `wacc.json` |
| `get_stock_dcf_analysis(symbol)` | `dcf_analysis.json` |
| `get_stock_ttm_pe`, `get_stock_enterprise_value`, `get_stock_enterprise_to_ebitda`, `get_stock_enterprise_to_revenue`, `get_stock_ps_ratio`, `get_stock_pb_ratio`, `get_stock_peg_ratio` | `valuation_multiples.json` (one file with each tool return under a labeled key) |
| `get_stock_quarterly_gross_margin`, `get_stock_quarterly_operating_margin`, `get_stock_quarterly_net_margin`, `get_stock_quarterly_ebitda_margin`, `get_stock_quarterly_fcf_margin` | `margins.json` (one file, 5 returns under labeled keys) |
| `get_stock_quarterly_revenue_yoy_growth`, `get_stock_quarterly_operating_income_yoy_growth`, `get_stock_quarterly_ebitda_yoy_growth`, `get_stock_quarterly_net_income_yoy_growth`, `get_stock_quarterly_fcf_yoy_growth`, `get_stock_quarterly_diluted_eps_yoy_growth` | `growth.json` (one file, 6 returns under labeled keys) |
| `get_stock_quarterly_roic`, `get_stock_quarterly_roe`, `get_stock_quarterly_roa`, `get_stock_quarterly_asset_turnover`, `get_stock_quarterly_equity_multiplier`, `get_stock_quarterly_debt_to_equity` | `capital_efficiency.json` (one file, 6 returns under labeled keys) |

**Period alignment:** transcript `fiscal_year`/`fiscal_quarter` must match the statement period. If you got the wrong transcript, re-call before Writing — once you Write, the cache file is treated as authoritative.

#### Tier 2 — call, then Write (with labeled fallback if MCP empty)

| MCP tool (primary) | Cache file |
|---|---|
| `get_quarterly_revenue_by_segment(symbol)` | `segment.json` |
| `get_quarterly_revenue_by_geography(symbol)` | `geography.json` |
| `get_industry_ttm_pe`, `get_industry_ps_ratio`, `get_industry_pb_ratio`, `get_industry_quarterly_gross_margin`, `get_industry_quarterly_ebitda_margin`, `get_industry_quarterly_net_margin`, `get_industry_quarterly_roa`, `get_industry_quarterly_roe`, `get_industry_quarterly_asset_turnover`, `get_industry_quarterly_equity_multiplier` | `industry.json` (one file, all industry returns under labeled keys) |

If a T2 MCP tool returns nothing, **separately Write the web fallback excerpt** to `./<TICKER>_<PERIOD>/cache/fallback_<topic>.txt`, including the source URL and retrieval date in the first line. Do not mix MCP and fallback content in the same file.

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

#### Reading the cache when drafting the report

**Before citing any number** in Phase 2 (analysis) or Phase 4 (DOCX), `Read` the corresponding cache file. Do not rely on numbers remembered from earlier in the conversation — context compression can paraphrase them. The cache file is the only authoritative source after Step 2.

Practical tips:
- For small cache files (`income_statement.json`, `market_cap.json`, `dcf_analysis.json`, etc.) — `Read` the whole file.
- For long ones (`transcript_current.txt` often 30K-60K chars, `industry.json` can be 500KB+) — `Read` with `offset` + `limit` to grab the specific section relevant to the paragraph you're writing.
- If two sections cite the same metric, prefer two narrowly-scoped `Read`s over one big `Read`. Re-reading is cheap; recovering a paraphrased number is impossible.

#### Verification before Step 3

Confirm before continuing to Step 3:
- `ls ./<TICKER>_<PERIOD>/cache/` shows every file from the Tier 1 and Tier 2 tables above (or, for genuine MCP gaps, the gap is documented and no T1 web patching happened)
- `transcript_current.txt` and `transcript_prior.txt` contain the expected fiscal periods (open and check the first lines if unsure)
- Tier 2 fallback files (if any) are clearly named `fallback_*.txt` and not mixed with MCP cache files

If something is missing or wrong, re-call the MCP tool and re-Write the cache file before continuing.

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
