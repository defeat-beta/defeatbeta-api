# Best Practices, Examples, and Quality Guidelines

This document provides examples, tips for success, common mistakes to avoid, and comprehensive quality checklists.

## Example Headlines

### Good Earnings Update Headlines:
- "Nike Q2 FY24: DTC Strength Offsets Wholesale Weakness - Maintaining OW, PT $95"
- "Tesla Q3'24: Cybertruck Ramp Ahead of Plan - Raising Estimates, PT to $285"
- "LVMH Q4'24: Fashion & Leather Resilient, Wines Weak - In-Line, Reiterating Buy"
- "Apple Q1 FY24: Services Beat, iPhone Miss - Mixed Quarter, Lowering PT to $185"

### Bad Headlines (Avoid):
- "Nike Quarterly Update" (too generic, no takeaway)
- "Company Reports Earnings" (states obvious, no analysis)
- "Q3 Results Analysis" (no company name, no view)

## Tips for Success

1. **Lead with conclusion**: Beat or miss? Up or down estimates?
2. **Quantify everything**: "Strong" means nothing — "$150M beat on $1.2B revenue (+12.5%)" is clear
3. **Focus on drivers**: Don't just say "revenue beat", explain WHY
4. **Show the work**: Old → New estimates with reasons
5. **Update price target if material**: If estimates change >5%, usually PT changes too
6. **Acknowledge the call**: Reference management commentary from the DefeatBeta MCP earnings call transcript
7. **Compare to peers**: If similar companies reported, note relative performance
8. **Be concise**: This is NOT a comprehensive report — stay focused on quarterly results
9. **Chart the trends**: Quarterly progression charts are most valuable

## Common Mistakes to Avoid

- **Too comprehensive**: Don't write an initiation-length report for quarterly results
- **Missing beat/miss**: Lead with whether results beat or missed expectations
- **Not updating estimates**: Must provide updated forward estimates
- **Vague language**: "Strong performance" without quantification
- **Ignoring guidance**: If company guides, analyze it thoroughly
- **Rehashing basics**: Don't spend 3 pages explaining what the company does
- **Missing price target update**: If estimates changed materially, PT should too
- **No investment impact**: Must connect results to thesis and rating
- **Unattributed data**: Every number needs the right citation for its tier (see SKILL.md Section 6)
- **Fabricating prior estimates**: if the user has no prior coverage on this name, stop and refer them to an initiation report (see SKILL.md Section 7) — don't invent old numbers to fill the Old vs. New columns

## Comprehensive Quality Control Checklist

Before delivering earnings update, verify all items below:

### Content & Analysis Checklist

**Beat/Miss Analysis:**
- [ ] Beat/miss analysis leads the report
- [ ] Specific variances quantified (e.g., "beat by $120M or 3%")
- [ ] Explanation of WHY results differed from expectations
- [ ] Analysis of each key metric (revenue, EPS, margins, etc.)

**Metrics & Performance:**
- [ ] All key metrics discussed with YoY comparisons
- [ ] QoQ comparisons included where relevant
- [ ] Segment/geographic/product breakdowns provided
- [ ] Operating metrics analyzed (customers, ARPU, units, etc.)

**Guidance & Estimates:**
- [ ] Guidance changes analyzed and quantified (if provided)
- [ ] If no guidance, this is explicitly noted
- [ ] Updated estimates provided for current year
- [ ] Updated estimates provided for next year
- [ ] Old vs. new estimates clearly shown
- [ ] Explanation of what changed and why

**Valuation & Rating:**
- [ ] Price target updated (if warranted by results)
- [ ] If PT unchanged, explicitly maintained
- [ ] Valuation methodology explained
- [ ] Rating confirmed or changed with clear rationale
- [ ] Investment thesis assessed and updated if needed

### Format & Length Checklist

**Overall Structure:**
- [ ] Report is 8-12 pages (not shorter, not longer)
- [ ] Page 1 has earnings summary format
- [ ] Page 1 has "EARNINGS UPDATE" in title (NOT "Initiating Coverage")
- [ ] Event-driven title (e.g., "Strong Q3 Results...")

**Tables:**
- [ ] 1-3 summary tables included (NOT comprehensive tables)
- [ ] All tables have clear column headers
- [ ] All tables have header row shading
- [ ] All tables have source lines at bottom
- [ ] Estimates table shows old vs. new with change column

**Charts:**
- [ ] 8-12 charts embedded throughout document
- [ ] All charts have "Figure X - [Title]" caption above
- [ ] All charts have "Source: [Source]" line below
- [ ] Charts focus on quarterly trends
- [ ] Charts highlight changes (beat/miss, revisions)
- [ ] Charts use professional styling

### Citations & Sources Checklist ⭐⭐⭐ MANDATORY

Every data point falls into Tier 1, 2, or 3 (see SKILL.md Section 5). The checklist below verifies each tier's specific source policy.

**Tier 1 — MCP only (no web fallback):**
- [ ] Reported income statement / balance sheet / cash flow cite the three quarterly statement MCP tools
- [ ] Earnings call transcript commentary cites `get_stock_earning_call_transcript` with fiscal year/quarter, report date, speaker, and paragraph number where available
- [ ] Stock price / market cap / WACC / EPS cite their MCP tools and retrieval date
- [ ] Valuation multiples (P/E, EV/EBITDA, P/S, P/B, PEG) cite the specific MCP tool used
- [ ] DCF / fair value cites `get_stock_dcf_analysis` (or notes that the `defeatbeta-dcf` skill was used)
- [ ] Margin / growth / ROIC etc. cite their specific MCP tools (gross/operating/net/EBITDA/FCF margin, YoY growth, ROIC/ROE/ROA, etc.)
- [ ] **For any T1 data MCP did not return, the report states the gap — no 10-Q, IR page, or news patched in**

**Tier 2 — MCP preferred, web fallback labeled:**
- [ ] Segment / geography revenue: MCP rows cite `get_quarterly_revenue_by_segment` / `get_quarterly_revenue_by_geography` with fiscal period
- [ ] Industry / peer comparables cite `get_industry_*` tools or labeled fallback
- [ ] Prior guidance cites prior-quarter `get_stock_earning_call_transcript` or labeled fallback (8-K, press release)
- [ ] Any fallback row is prefixed `Fallback source:` and includes URL, retrieval date, and a brief note on why MCP did not cover it
- [ ] Fallback rows are visually separate from MCP rows in figures, tables, and the Sources section

**Tier 3 — Web only (MCP does not cover):**
- [ ] Consensus estimates cite a named source (Bloomberg / FactSet / Yahoo / TipRanks / etc.) with "as of" date — pre-earnings close where possible
- [ ] Analyst price targets cite source + retrieval date + analyst count if available
- [ ] Operating metrics (DAU/MAU/ARPU, customer count, store count, etc.) cite company IR / 10-Q supplementary / investor presentation with URL + retrieval date
- [ ] Stock reaction history cites source + date range
- [ ] Options-implied move (if used) cites the options data provider + retrieval date
- [ ] Recent news / policy catalysts cite outlet + URL + retrieval date

**Sources section structure:**
- [ ] "Sources & References" section at end of report
- [ ] Grouped explicitly by **Tier 1 / Tier 2 / Tier 3**
- [ ] Tier 1 lists every MCP tool actually used (statement, transcript, market, valuation, margin, growth, efficiency)
- [ ] Tier 2 lists MCP segment/geography/industry tools and any fallback sources (clearly labeled)
- [ ] Tier 3 lists consensus, analyst targets, operating-metric source, news, etc., each with "as of" or retrieval date

### Accuracy Checklist

**Numerical Accuracy:**
- [ ] Numbers match DefeatBeta MCP reported results exactly
- [ ] Math checks out in all calculations
- [ ] Estimate changes calculated correctly
- [ ] Valuation math is accurate
- [ ] Charts match text descriptions

**Factual Accuracy:**
- [ ] No typos in ticker symbol
- [ ] No typos in company name
- [ ] Dates are current and accurate
- [ ] Quarter/year references are correct
- [ ] Year notation correct (A for actual, E for estimate)

### Period & Data Currency Checklist

- [ ] All reported financial data is from the selected MCP fiscal period (verified against `periods` arrays)
- [ ] Consensus estimates are pre-earnings where available (cite "as of <date>")
- [ ] MCP transcript report date matches the statement period; no mismatched fiscal years/quarters

### Writing Style Checklist

**Clarity & Directness:**
- [ ] Lead with numbers ("Revenue grew 15% to $1.2B" not "Strong revenue")
- [ ] Use "vs." not "versus"
- [ ] Be direct and concise throughout
- [ ] Focus on what's NEW (not rehashing company basics)
- [ ] Avoid vague language ("strong performance" without quantification)
- [ ] Report, delivery summary, replies, visible rationale, assumptions, and methodology explanations match the user's language

**Professional Standards:**
- [ ] Institutional tone maintained
- [ ] Consistent terminology throughout
- [ ] No informal language
- [ ] Proper financial notation

## Pre-Delivery Final Check

Run through this quick final check before sending report to user:

### 5-Minute Final Review:
1. **Page 1**: Rating clear? Price target updated? Key takeaways compelling?
2. **Numbers**: Do reported results match DefeatBeta MCP statement data exactly?
3. **Citations**: Spot check 3-4 figures/tables - all have specific MCP tool attribution?
4. **Estimates**: Old vs. new clearly shown? Changes explained?
5. **Charts**: All 8-12 embedded? All numbered and captioned?
6. **Length**: Is it 8-12 pages (not 6, not 15)?
7. **Sources**: Does the sources section list all MCP tools used?
8. **Prior coverage**: Was prior estimates / rating / PT actually provided? If not, the report should not have been written.

If all items check out, the report is ready for delivery.

## Summary Delivery Format

When delivering the completed report to the user, provide this summary:

```
[Company] Q[X] [Year] Earnings Update Complete

Results: [BEAT / INLINE / MISS]
- Revenue: $X.XB ([beat/missed] by $XXM or X%)
- EPS: $X.XX ([beat/missed] by $X.XX)

Key Takeaways:
■ [Takeaway 1]
■ [Takeaway 2]
■ [Takeaway 3]

Updated Estimates:
- FY[Year]E Revenue: $XX.XB (prior: $XX.XB, [+/-]X%)
- FY[Year]E EPS: $X.XX (prior: $X.XX, [+/-]X%)

Rating: [MAINTAINED / RAISED / LOWERED] [RATING]
Price Target: $XXX (prior: $XXX) — [+/-]XX% upside

Deliverables:
- 8-12 page earnings update report (DOCX)
- 8-12 embedded charts
- Updated estimates with old/new comparison
- Sources section grouped by Tier 1 / Tier 2 / Tier 3
- [Optional: Updated XLS financial model]

File: [Company]_Q[X]_[Year]_Earnings_Update.docx
```
