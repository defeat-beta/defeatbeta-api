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

Tier 1 and Tier 2 data are retrieved by running the `collect_data.py` helper script, which imports the MCP tool functions directly and writes one file per data domain to a local directory. **Do not call MCP tools individually for Tier 1 / Tier 2 data** — every call returns a large JSON payload that goes straight into the assistant's context, and pulling 20+ tools that way reliably triggers context compaction.

#### Tier 1 + Tier 2 — Run the bundle script

```bash
python <SKILL_DIR>/scripts/collect_data.py \
    --ticker <SYMBOL> \
    --output-dir <PATH>
# Optional: --fiscal-year YYYY --fiscal-quarter Q  (defaults to latest)
```

The script:
- Calls `get_latest_data_update_date` and `get_stock_earning_call_transcripts_list` to pick the target fiscal period
- Pulls all Tier 1 data (3 statements, current + prior transcript, price/market cap/WACC/EPS, valuation multiples, margins, growth, capital efficiency)
- Pulls all Tier 2 data (segment, geography, industry comparables)
- Writes each domain to a separate JSON/TXT file in `--output-dir`
- Fail-fast: if any tool errors, the script exits with nonzero — handle the error, surface to the user, do **not** patch from web

After the script runs, **Read only the file you need** for each report-writing step. See SKILL.md Section 5 "Where data lives after `collect_data.py`" for the file → content map. Files are typically 10KB-2MB; use `Read` with line ranges on large files rather than reading the whole thing.

**Period alignment** is automatic — the script selects the same `fiscal_year` / `fiscal_quarter` for transcript and statements. The values are recorded in `_summary.json` for verification.

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

Read `_summary.json` to confirm:
- `target_period.fiscal_year` / `target_period.fiscal_quarter` match what the user asked for (or latest if unspecified)
- `prior_period` exists if you intend to write a prior-guidance comparison
- All expected file paths under `files` are present on disk

If something is missing, re-run `collect_data.py`. Do not proceed with mismatched periods.

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
