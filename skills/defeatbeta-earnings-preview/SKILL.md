---
name: defeatbeta-earnings-preview
description: "Build pre-earnings analysis with estimate models, scenario frameworks, and key metrics to watch. Use before a company reports quarterly earnings to prepare positioning notes, set up bull/base/bear scenarios, and identify what will move the stock. Triggers on earnings preview, what to watch for company earnings, pre-earnings, earnings setup, or preview Q[X] for a company."
argument-hint: <TICKER> <FISCAL_QUARTER>
compatibility: Requires defeatbeta MCP server
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

### Step 5: Output

One-page earnings preview with:
- Company, quarter, earnings date
- Consensus estimates table
- Prior-quarter management guidance from the defeatbeta MCP server transcript tools
- Key metrics to watch, ranked by importance
- Bull/base/bear scenario table
- Catalyst checklist
- Trading setup: recent stock performance and implied move from options

## Important Notes

- Consensus estimates change, so always note the source and date of estimates
- Prior-quarter management guidance must come from the defeatbeta MCP server transcript tools, not web search
- Whisper numbers from buy-side surveys are often more relevant than published consensus
- Historical earnings reactions help calibrate expectations; search for "[company] earnings reaction history"
- Options-implied move tells you what the market expects; compare it to your scenarios
