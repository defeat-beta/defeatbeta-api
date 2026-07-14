---
name: defeatbeta-earnings-preview
description: "Build pre-earnings analysis with estimate models, scenario frameworks, key metrics, catalysts, historical reactions, and options-implied moves. Use before a company reports quarterly earnings to prepare positioning notes or bilingual three-page PDF reports. Triggers on earnings preview, what to watch for company earnings, pre-earnings, earnings setup, preview Q[X] for a company, or requests for an earnings-preview report/PDF."
---

# Earnings Preview

Build pre-earnings analysis with estimate models, scenario frameworks, and key metrics to watch. Use before a company reports quarterly earnings to prepare positioning notes, set up bull/base/bear scenarios, and identify what will move the stock.

## Workflow

### Step 1: Gather Context

- Identify the company and reporting quarter
- Pull consensus estimates via web search, including revenue, EPS, and key segment metrics
- Find the earnings date and time, including whether the report is pre-market or after-hours
- Review management guidance and commentary from the prior quarter's earnings call by using the defeatbeta MCP server transcript tools:
  - First call `get_stock_earning_call_transcripts_list(symbol)` to identify available earnings call transcripts and select the most recent reported fiscal quarter
  - Then call `get_stock_earning_call_transcript(symbol, fiscal_year, fiscal_quarter)` to retrieve the full transcript for that fiscal period
  - Extract management guidance, outlook, demand commentary, margin commentary, capital allocation comments, and any explicit forward-looking statements from the transcript
  - Do not use web search as a substitute for prior-quarter management guidance; if the MCP transcript tools return no transcript or are unavailable, explicitly state the data gap

### Step 2: Key Metrics Framework

Build a "what to watch" framework specific to the company:

**Financial Metrics:**
- Revenue vs. consensus, total and by segment
- EPS vs. consensus
- Margins, including gross, operating, and net margin
- Free cash flow
- Forward guidance vs. consensus

**Operational Metrics** (sector-specific):
- Tech/SaaS: ARR, net retention, RPO, customer count
- Retail: Same-store sales, traffic, basket size
- Industrials: Backlog, book-to-bill, price vs. volume
- Financials: NIM, credit quality, loan growth, fee income
- Healthcare: Scripts, patient volumes, pipeline updates

### Step 3: Scenario Analysis

Build three scenarios with stock price implications:

| Scenario | Revenue | EPS | Key Driver | Stock Reaction |
|----------|---------|-----|------------|----------------|
| Bull | | | | |
| Base | | | | |
| Bear | | | | |

For each scenario:
- What would need to happen operationally
- What management commentary would signal this
- Historical context, including how the stock has moved on similar prints

### Step 4: Catalyst Checklist

Identify the three to five things that will determine the stock's reaction:

1. [Metric] vs. [consensus/whisper number] - why it matters
2. [Guidance item] - what the buy-side expects to hear
3. [Narrative shift] - any strategic changes, M&A, restructuring

### Step 5: Choose the Output Format

- For a concise chat response or positioning note, produce a one-page earnings preview with the company, quarter, earnings date, consensus table, prior-quarter guidance, ranked metrics, bull/base/bear scenarios, catalysts, recent stock performance, and options-implied move.
- When the user requests a report/PDF or supplies a reference PDF, produce a three-page A4 PDF using the bundled AMD example as the visual and structural reference.
- Select the template by the user's requested language. If no language is specified, use the language of the user's request:
  - Chinese: `assets/earnings-preview-template-zh.pdf`
  - English: `assets/earnings-preview-template-en.pdf`
- Treat the bundled template as a complete worked example, not a form. Preserve its design system, content density, section order, tables, and page structure while replacing all company-specific content with the target company's data.
- Do not strip or neutralize the AMD content inside the template assets. Use it to calibrate the expected level of analytical detail and layout density.

### Step 6: Build the Three-Page PDF

Use this structure unless the user explicitly requests another format:

**Page 1**
- Title, reporting date and time, data cutoff date
- Core view
- Consensus estimates vs. management guidance
- Prior-quarter management signals from DefeatBeta transcripts

**Page 2**
- Five ranked company- and sector-specific metrics
- Bull/base/bear scenario table with revenue, EPS, operational conditions, and stock reactions
- Three to five catalysts

**Page 3**
- Recent stock performance and four historical earnings reactions
- Options-implied move and implied price range
- Suggested manual tracking plan through the reporting date
- Clickable data sources and risk disclosure

Adapt operational metrics to the company. Do not mechanically carry semiconductor metrics into software, retail, financial, industrial, or healthcare reports.

If part of the quarter is already known from monthly revenue, regulatory data, unit sales, or another disclosed operating statistic, explicitly separate known results from remaining uncertainties. Refocus the core view and scenarios on the variables that can still surprise the market, such as margins, segment mix, forward guidance, or management commentary.

### Step 7: Add Source Links

- Make every named public source in the PDF clickable and link directly to the supporting page, not a search-results page.
- Link `DefeatBeta MCP` to `https://github.com/defeat-beta/defeatbeta-api` wherever it appears as a source.
- State the access date for consensus estimates, stock prices, and options data.
- Explicitly state when a reliable public segment consensus or buy-side whisper number cannot be verified.
- Label inferences, scenario thresholds, and estimated market hurdles as research judgments rather than published consensus.

### Step 8: Validate the PDF

- Render every page to images and visually inspect typography, line wrapping, tables, spacing, headers, footers, and page numbers.
- Confirm the report is three A4 pages with no clipped text, overlaps, missing glyphs, black squares, or broken tables.
- Verify the PDF contains clickable link annotations for each named source.
- Search the final text for template leakage. Unless the target company is AMD, remove residual terms such as `AMD`, `MI450`, `Helios`, `EPYC`, and `Instinct`.
- Confirm the company name, fiscal quarter, reporting date, metrics, scenarios, prices, and sources all belong to the target company.
- State that a tracking plan is a suggested manual cadence and does not mean an automation, reminder, or monitor was created.

## Important Notes

- Consensus estimates change, so always note the source and date of estimates
- Prior-quarter management guidance must come from the defeatbeta MCP server transcript tools, not web search
- Whisper numbers from buy-side surveys are often more relevant than published consensus
- Historical earnings reactions help calibrate expectations; search for "[company] earnings reaction history"
- Options-implied move tells you what the market expects; compare it to your scenarios
- Options ranges captured well before earnings include ordinary pre-event volatility; do not describe them as pure overnight earnings moves
- Preserve source dates and data gaps in both the narrative and the PDF
