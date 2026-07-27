---
name: defeatbeta-earnings-preview
description: Build pre-earnings analysis with normalized baselines, weighted decision models, company-specific veto gates, scenario frameworks, catalysts, historical reactions, and options-implied moves. Use before a company reports quarterly earnings to prepare positioning notes or bilingual three-page PDF reports.
---

# DefeatBeta Earnings Preview

Create a decision-ready pre-earnings report. Anchor every threshold to sourced consensus, management guidance, prior-quarter financial statements, and company-specific operating drivers.

## 1. Establish the Reporting Context

1. Confirm the company, ticker, fiscal quarter, reporting date, and expected release timing.
2. Gather current consensus estimates and link the source.
3. Use DefeatBeta to retrieve the latest available prior-quarter earnings call:
   - Call `get_stock_transcript_list` first.
   - Call `get_stock_transcript` with the exact returned quarter and year.
   - Extract management guidance, operating targets, risks, and unresolved questions.
4. Use DefeatBeta to retrieve the latest reported quarterly statements:
   - `get_stock_quarterly_income_statement`
   - `get_stock_quarterly_balance_sheet`
   - `get_stock_quarterly_cash_flow`
5. Separate three information states:
   - **Reported:** historical facts from statements or filings.
   - **Guided:** explicit management targets or qualitative commitments.
   - **Estimated:** consensus or analyst judgment.
6. If any required source is unavailable, disclose the gap. Do not replace prior-quarter guidance with web snippets.

## 2. Build a Normalized Starting Point

Create a compact baseline bridge before forecasting the next quarter:

| Metric | Prior Reported | Normalization Item | Normalized Baseline | Current Hurdle | Source |
|---|---:|---|---:|---:|---|

Review at least:

- Revenue and segment mix
- Gross margin and the company-specific profitability metric
- Operating expenses, including R&D where material
- Operating margin
- Operating cash flow
- Working-capital contribution
- Capital expenditures
- Free cash flow
- Diluted share count

Identify material one-time or low-repeatability items such as regulatory credits, warranty adjustments, tariffs, restructuring, asset revaluations, foreign exchange, investment marks, tax effects, and unusual working-capital movements.

Label every normalization as analyst judgment. Never present a normalized figure as a reported fact.

## 3. Rank the Decision Metrics

Select five to eight company-specific dimensions. Rank them by:

1. Earnings materiality
2. Probability of surprise
3. Expected stock-price sensitivity

Cover the following when material:

- Revenue and segment mix
- EPS and earnings quality
- Gross margin and the most relevant unit-economics metric
- Operating expenses and operating margin
- Operating cash flow, working capital, capital expenditures, and free cash flow
- Forward guidance
- Company-specific operating metrics

Do not use generic metrics when a better company-specific measure exists.

## 4. Use a Weighted Decision Model

Assign explicit weights totaling 100%. Use five to eight dimensions. A typical starting range is:

- Profitability and margin quality: 20% to 35%
- EPS and earnings quality: 10% to 20%
- Revenue and mix: 10% to 25%
- Operating expenses and capital intensity: 10% to 20%
- Cash conversion: 5% to 15%
- Company-specific operating or commercial milestones: 10% to 25%
- Balance-sheet risk: 0% to 10%

Score each dimension from -2 to +2:

- `+2`: clear Bull outcome
- `+1`: modestly positive
- `0`: Base or in line
- `-1`: modestly negative
- `-2`: clear Bear outcome

Calculate:

`Weighted Score = sum(weight × dimension score ÷ 2)`

The score ranges from -1.0 to +1.0. Use default bands unless company history supports better thresholds:

- **Bull:** score at or above +0.35 and no veto gate triggered
- **Base:** score between -0.35 and +0.35 and no veto gate triggered
- **Bear:** score at or below -0.35, or any Bear veto gate triggered

Show the selected weights and score logic in the report. Revenue and EPS ranges are reference outcomes, not a requirement that every scenario condition occur together.

### Define Company-Specific Veto Gates

Add two to five objective Bear veto gates. A veto gate overrides the weighted score. Adapt the gates to the company and sector.

Examples:

- Profitability falls below a structurally important threshold.
- Forward guidance is materially below consensus.
- A core product launch, capacity ramp, approval, or delivery milestone slips.
- Operating expenses or capital intensity rise without a credible commercialization bridge.
- Liquidity, leverage, credit loss, subscriber churn, or another sector-specific risk breaches a critical level.
- Reported earnings are supported by non-operating or low-repeatability items while operating earnings deteriorate.

Use precise thresholds whenever the evidence supports them. Explain why each threshold matters.

### Validate Mixed Signals

Test the model before publishing with at least one mixed case, such as:

- Revenue scores Base.
- Free cash flow scores Bull.
- Profitability scores Bear.

The framework must return one overall scenario and explain whether the weighted score or a veto gate determined it. Eliminate overlapping or ambiguous scenario outcomes.

## 5. Separate Progress from Monetization

For every major catalyst, classify the evidence:

1. **Technical progress:** prototype, benchmark, approval, or product readiness
2. **Operating scale:** capacity, deployment, production, or service availability
3. **User adoption:** customers, usage, retention, or engagement
4. **Commercial contribution:** pricing, contracted revenue, recognized revenue, margin, or cash flow

State which evidence level has been reached and what must occur next. Do not allow technical progress alone to offset weak economics unless the investment thesis explicitly supports that trade-off.

## 6. Choose the Deliverable

### Concise Note

Use a compact table-first format when the user requests a quick preview or chat response.

### Three-Page PDF

Use the matching template:

- Chinese: `assets/earnings-preview-template-zh.pdf`
- English: `assets/earnings-preview-template-en.pdf`

Preserve the template's design system, content density, table hierarchy, and three-page A4 format. Replace all worked-example content and remove all template-company leakage.

Use the completed AMD reports as quality references when a realistic example is useful:

- Chinese: `assets/amd-fy2026-q2-earnings-preview-zh.pdf`
- English: `assets/amd-fy2026-q2-earnings-preview-en.pdf`

Use these completed examples to calibrate evidence separation, normalization detail, weighted scoring, veto gates, source links, and release-day usability. Never reuse their company data, dates, thresholds, consensus, or conclusions in another report.

## 7. Structure the Three-Page PDF

### Page 1: Setup and Normalized Baseline

- Title, reporting date, and core view
- Consensus versus management guidance
- Reported, guided, and estimated information
- Prior-quarter reported baseline
- One-time items and normalization bridge
- Known facts versus unresolved uncertainties

### Page 2: Decision Framework

- Five to eight ranked metrics with weights
- Weighted score method and scenario bands
- Bull, Base, and Bear reference ranges
- Company-specific Bear veto gates
- Catalysts classified by commercialization maturity

### Page 3: Trading and Release Plan

- Historical post-earnings reactions with consistent measurement windows
- Options-implied move and method
- Ten-minute post-release checklist
- Post-release tracking plan
- Linked sources and risk disclosure

## 8. Build the Trading Setup Carefully

For historical reactions, use the same observation window across quarters whenever possible. Label whether the move is:

- After-hours
- Next open
- Next close
- Two-day close

For the options-implied move, state:

- Observation date and time
- Expiration used
- Calculation method
- Whether the estimate is an overnight move or a move through expiration

Do not compare inconsistent reaction windows without disclosure.

## 9. Add a Ten-Minute Release Checklist

Organize the checklist by elapsed time:

- **0 to 2 minutes:** headline revenue, EPS, guidance, and veto gates
- **2 to 5 minutes:** segment mix, margins, operating expenses, and one-time items
- **5 to 8 minutes:** operating cash flow, working capital, capital expenditures, and free cash flow
- **8 to 10 minutes:** operating milestones, commercialization evidence, weighted score, and final scenario

The checklist must make the report usable during the release rather than only descriptive before it.

## 10. Cite Sources

Use linked primary or reputable sources. Include:

- DefeatBeta transcript and financial statement data
- Company investor relations materials
- Consensus estimate source
- Historical price-reaction source
- Options-implied move source or calculation method

Use live clickable links in the PDF.

## 11. Validate Before Delivery

Confirm:

- The PDF contains exactly three A4 pages.
- Both Chinese and English templates remain readable after rendering.
- All external links are clickable.
- Weights total 100%.
- Scenario bands have no gaps or overlaps.
- Veto gates produce one unambiguous final scenario.
- A mixed-signal test resolves to one scenario.
- Reported, guided, estimated, and normalized values are clearly separated.
- Quarterly free cash flow is separated from working-capital quality and multi-year capital intensity.
- Technical milestones are separated from commercial contribution.
- No worked-example company, ticker, dates, or metrics remain in the final report.

## Important Notes

- This is an earnings preview, not an earnings update.
- Treat scenario outputs as a decision framework, not a point forecast.
- Use neutral investment-research language.
- Do not fabricate missing values.
- Clearly distinguish sourced facts from analyst judgment.
