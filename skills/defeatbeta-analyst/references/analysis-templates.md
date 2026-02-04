# Financial Analysis Templates

Detailed workflow templates for common financial analysis tasks using defeatbeta-api.

## Template 1: Quick Investment Screening

**Use case**: Fast evaluation of whether a stock warrants deeper analysis

**Workflow**:
```
1. get_latest_data_update_date
   → Establish reference date

2. get_stock_profile
   → Understand business model
   → Check sector/industry
   → Note if financial institution (affects ROIC applicability)

3. get_stock_price (last 6 months)
   → Recent price trend
   → Volatility assessment

4. get_stock_quarterly_income_statement (last 4 quarters)
   → Revenue trend
   → Profitability check

5. get_stock_ttm_pe (last 3 years)
   → Current valuation vs historical
   → Identify extreme values

6. get_industry_ttm_pe (last 3 years)
   → Peer valuation comparison

7. get_stock_quarterly_revenue_yoy_growth
   → Growth momentum
```

**Decision criteria**:
- ✅ Pass: Revenue growing, P/E below historical/industry average, positive margins
- ❌ Skip: Revenue declining, P/E at multi-year highs, negative margins
- 🔍 Deep dive: Mixed signals, needs detailed analysis

---

## Template 2: Full Fundamental Analysis

**Use case**: Comprehensive evaluation for investment decision

**Workflow**:

### Phase 1: Business Understanding
```
1. get_latest_data_update_date
2. get_stock_profile
   → Business model, competitive position
3. get_stock_officers
   → Management team
4. get_quarterly_revenue_by_segment
   → Business mix, growth drivers
5. get_quarterly_revenue_by_geography
   → Geographic exposure, concentration risk
6. get_stock_news (last 6 months, max_rows=20)
   → Recent developments
```

### Phase 2: Financial Health
```
7. get_stock_quarterly_balance_sheet (last 8 quarters)
   → Asset composition
   → Debt levels
   → Liquidity position (current ratio)

8. get_stock_quarterly_cash_flow (last 8 quarters)
   → Operating cash flow trends
   → FCF consistency
   → Capital allocation (capex, buybacks, dividends)
```

### Phase 3: Profitability Analysis
```
9. get_stock_quarterly_gross_margin (last 12 quarters)
10. get_stock_quarterly_operating_margin
11. get_stock_quarterly_net_margin
12. get_stock_quarterly_fcf_margin
   → Margin trends and sustainability

13. get_industry_quarterly_gross_margin
14. get_industry_quarterly_net_margin
   → Industry comparison

15. get_stock_quarterly_roe (last 12 quarters)
16. get_stock_quarterly_roa
17. get_stock_quarterly_roic (if not bank)
   → Return metrics and trends
```

### Phase 4: Growth Assessment
```
18. get_stock_quarterly_revenue_yoy_growth
19. get_stock_quarterly_operating_income_yoy_growth
20. get_stock_quarterly_net_income_yoy_growth
21. get_stock_quarterly_fcf_yoy_growth
22. get_stock_quarterly_ttm_diluted_eps_yoy_growth
   → Multi-metric growth analysis
   → Check for earnings quality (is earnings growing faster than revenue?)
```

### Phase 5: Valuation
```
23. get_stock_ttm_pe (last 5 years)
24. get_stock_ps_ratio (last 5 years)
25. get_stock_pb_ratio (last 5 years)
26. get_stock_peg_ratio (last 3 years)
   → Historical valuation context

27. get_industry_ttm_pe (current)
28. get_industry_ps_ratio (current)
29. get_industry_pb_ratio (current)
   → Peer valuation comparison
```

### Phase 6: Synthesis
- Compile findings into investment thesis
- Identify key risks and opportunities
- Determine fair value range
- Make recommendation (buy/hold/sell)

---

## Template 3: Valuation-Focused Analysis

**Use case**: Determine if stock is overvalued/undervalued

**Workflow**:
```
1. get_latest_data_update_date

2. Current Valuation Snapshot
   → get_stock_ttm_pe (current)
   → get_stock_ps_ratio (current)
   → get_stock_pb_ratio (current)
   → get_stock_market_capitalization (current)

3. Historical Valuation Context (5 years)
   → get_stock_ttm_pe (5y range)
   → get_stock_ps_ratio (5y range)
   → get_stock_pb_ratio (5y range)
   → Calculate percentile ranks (current vs historical)

4. Peer Comparison
   → get_industry_ttm_pe (current + 3y history)
   → get_industry_ps_ratio (current + 3y history)
   → get_industry_pb_ratio (current + 3y history)

5. Growth-Adjusted Valuation
   → get_stock_peg_ratio (current)
   → get_stock_quarterly_ttm_diluted_eps_yoy_growth
   → get_stock_quarterly_revenue_yoy_growth

6. Quality Justification
   → get_stock_quarterly_roe (margins justify premium?)
   → get_stock_quarterly_roic (returns justify premium?)
   → get_stock_quarterly_gross_margin (pricing power)

7. Market Context
   → get_sp500_cagr_returns (10y)
   → get_daily_treasury_yield (current 10y)
   → Calculate equity risk premium
```

**Valuation signals**:
- **Cheap**: P/E < historical average AND < industry average AND PEG < 1.5
- **Fair**: P/E near historical/industry average AND PEG 1.5-2.0
- **Expensive**: P/E > historical average AND > industry average AND PEG > 2.5
- **Growth premium justified**: High P/E but ROE > industry AND revenue growth > 20%

---

## Template 4: Growth Quality Assessment

**Use case**: Evaluate if revenue/earnings growth is sustainable and high-quality

**Workflow**:
```
1. get_latest_data_update_date

2. Top-Line Growth
   → get_stock_quarterly_revenue_yoy_growth (last 12 quarters)
   → get_quarterly_revenue_by_segment (identify drivers)
   → get_quarterly_revenue_by_geography (diversification)

3. Margin Expansion Check
   → get_stock_quarterly_gross_margin (last 12 quarters)
   → get_stock_quarterly_operating_margin
   → get_stock_quarterly_net_margin
   → Is margin expanding? (sign of pricing power/efficiency)

4. Earnings Quality
   → get_stock_quarterly_net_income_yoy_growth
   → Compare to revenue growth
   → If earnings growing faster = margin expansion (good)
   → If earnings growing slower = margin compression (concern)

5. Cash Conversion
   → get_stock_quarterly_cash_flow (last 12 quarters)
   → get_stock_quarterly_fcf_yoy_growth
   → FCF / Net Income ratio (>80% is strong)
   → Operating cash flow trend

6. Investment Requirements
   → get_stock_quarterly_cash_flow (capex trends)
   → Capex / Revenue ratio
   → R&D / Revenue ratio (from income statement)
   → High and increasing = growth requires significant investment

7. Balance Sheet Impact
   → get_stock_quarterly_balance_sheet (last 8 quarters)
   → Is debt increasing to fund growth? (concerning)
   → Is equity increasing (dilution)?
   → Working capital changes

8. Returns on Invested Capital
   → get_stock_quarterly_roic (if not bank)
   → Is ROIC > WACC? (value creation)
   → Is ROIC improving? (efficiency gains)
```

**Quality signals**:
- ✅ **High quality**: FCF > Net Income, ROIC improving, margins expanding, low capex intensity
- ⚠️ **Medium quality**: FCF = Net Income, ROIC stable, margins flat, moderate capex
- ❌ **Low quality**: FCF < Net Income, ROIC declining, margins compressing, high capex needs

---

## Template 5: DuPont Analysis Deep Dive

**Use case**: Decompose ROE to understand profitability drivers

**Workflow**:
```
1. get_latest_data_update_date

2. Get DuPont Components (last 12 quarters)
   → get_stock_quarterly_roe
   → get_stock_quarterly_roa
   → get_stock_quarterly_net_margin
   → get_stock_quarterly_asset_turnover
   → get_stock_quarterly_equity_multiplier (if not bank)

3. Validate DuPont Identity
   → ROE = Net Margin × Asset Turnover × Equity Multiplier
   → ROE = ROA × Equity Multiplier
   → Asset Turnover = ROA / Net Margin

4. Identify Primary ROE Driver
   → High net margin = pricing power, brand strength (e.g., luxury goods)
   → High asset turnover = operational efficiency (e.g., retailers)
   → High equity multiplier = financial leverage (check if sustainable)

5. Trend Analysis
   → Which component is improving/deteriorating?
   → Net margin trends (profitability)
   → Asset turnover trends (efficiency)
   → Equity multiplier trends (leverage)

6. Industry Comparison
   → get_industry_quarterly_roe
   → get_industry_quarterly_roa
   → get_industry_quarterly_net_margin
   → get_industry_quarterly_asset_turnover
   → get_industry_quarterly_equity_multiplier
   → Which component drives industry ROE?
   → Where does company outperform/underperform?

7. Strategic Implications
   → Low margin, high turnover = compete on efficiency
   → High margin, low turnover = compete on differentiation
   → Increasing leverage = growth focus or financial stress?
```

**DuPont profiles**:
- **Brand/Luxury**: High margin (>20%), Low turnover (<0.5), Low leverage (<2x)
- **Retailer**: Low margin (<5%), High turnover (>2), Moderate leverage (2-3x)
- **Tech**: High margin (>15%), Moderate turnover (0.5-1), Low leverage (<2x)
- **Industrial**: Moderate margin (10-15%), Low turnover (<1), Moderate leverage (2-3x)

---

## Template 6: DCF Model Data Preparation

**Use case**: Gather inputs for discounted cash flow valuation

**Workflow**:
```
1. get_latest_data_update_date

2. Historical Free Cash Flow (5 years)
   → get_stock_annual_cash_flow
   → Extract FCF for last 5 years
   → Calculate average FCF
   → Identify trend (growing/stable/declining)

3. Growth Rate Estimation
   → get_stock_annual_revenue_yoy_growth (5 years)
   → get_stock_annual_fcf_yoy_growth (5 years)
   → Calculate weighted average growth rate
   → Adjust for sustainability (cap at industry growth)

4. Discount Rate (WACC)
   → get_stock_wacc (current)
   → Verify components:
     - Risk-free rate (10y Treasury)
     - Beta (5-year)
     - Market return (S&P 500 10y CAGR)
     - Debt/Equity weights
     - Cost of debt

5. Terminal Value Inputs
   → get_stock_quarterly_balance_sheet (latest)
   → Book value for sanity check
   → get_industry_quarterly_roe (perpetuity growth proxy)
   → Assume terminal growth = 2-3% (GDP growth)

6. Shares Outstanding
   → get_stock_market_capitalization (current)
   → get_stock_price (current)
   → Calculate shares: Market Cap / Price

7. Sensitivity Analysis Inputs
   → Growth rate range: Base ± 2%
   → WACC range: Base ± 1%
   → Terminal growth range: 1.5% - 3.5%

8. Sanity Checks
   → P/E implied by DCF vs current P/E
   → DCF value vs book value (reasonable premium?)
   → Compare to industry average valuations
```

**DCF calculation structure**:
```
Year 1-5: FCF × (1 + growth_rate)^year
Terminal Value: Year_5_FCF × (1 + terminal_growth) / (WACC - terminal_growth)
PV = Σ(FCF / (1 + WACC)^year) + (Terminal_Value / (1 + WACC)^5)
Equity Value = PV - Net Debt
Price per share = Equity Value / Shares Outstanding
```

---

## Template 7: Margin Analysis & Peer Comparison

**Use case**: Evaluate operational efficiency and competitive positioning

**Workflow**:
```
1. get_latest_data_update_date

2. Company Margin Cascade (last 12 quarters)
   → get_stock_quarterly_gross_margin
   → get_stock_quarterly_operating_margin
   → get_stock_quarterly_ebitda_margin
   → get_stock_quarterly_net_margin
   → get_stock_quarterly_fcf_margin

3. Margin Trends
   → Are margins expanding or compressing?
   → Consistent or volatile?
   → Seasonal patterns?

4. Industry Benchmarks (same periods)
   → get_industry_quarterly_gross_margin
   → get_industry_quarterly_net_margin
   → get_industry_quarterly_ebitda_margin

5. Competitive Position
   → Gross margin vs industry (pricing power)
   → Operating margin vs industry (cost control)
   → Net margin vs industry (overall efficiency)

6. Margin Bridge Analysis
   → Gross margin → Operating margin (SG&A efficiency)
   → Operating margin → EBITDA margin (D&A intensity)
   → EBITDA margin → Net margin (interest/tax burden)
   → Net margin → FCF margin (working capital/capex needs)

7. Margin Drivers Investigation
   → get_stock_quarterly_income_statement
   → COGS / Revenue (cost structure)
   → R&D / Revenue (innovation intensity)
   → SG&A / Revenue (overhead burden)
   → Interest / Revenue (leverage cost)
```

**Margin interpretation**:
- **Gross margin**: Product pricing power, cost of goods efficiency
- **Operating margin**: Overall operational efficiency
- **EBITDA margin**: Core business profitability (before capital structure)
- **Net margin**: Bottom-line profitability after all costs
- **FCF margin**: Cash generation ability (quality of earnings)

---

## Template 8: Earnings Quality Assessment

**Use case**: Determine if reported earnings reflect true economic performance

**Workflow**:
```
1. get_latest_data_update_date

2. Cash vs Accrual Earnings (last 12 quarters)
   → get_stock_quarterly_income_statement
   → get_stock_quarterly_cash_flow
   → Compare Net Income to Operating Cash Flow
   → High quality: OCF > Net Income consistently

3. Free Cash Flow Quality
   → get_stock_quarterly_cash_flow
   → FCF = Operating Cash Flow - Capex
   → FCF / Net Income ratio
   → Target: >80% indicates strong conversion

4. Working Capital Analysis
   → get_stock_quarterly_balance_sheet
   → get_stock_quarterly_cash_flow
   → Changes in receivables, inventory, payables
   → Growing receivables/inventory = concern

5. Revenue Quality
   → get_stock_quarterly_revenue_yoy_growth
   → get_stock_quarterly_balance_sheet
   → Days Sales Outstanding (DSO) = (Receivables / Revenue) × 90
   → Increasing DSO = deteriorating revenue quality

6. Margin Sustainability
   → get_stock_quarterly_gross_margin
   → get_stock_quarterly_operating_margin
   → Are margins improving artificially (cost cutting)?
   → Or structurally (pricing power)?

7. Capital Allocation
   → get_stock_quarterly_cash_flow
   → Capex trends (maintenance vs growth)
   → Share buybacks (value creation or manipulation?)
   → Dividends (sustainable payout ratio?)

8. One-Time Items Check
   → get_stock_quarterly_income_statement
   → Restructuring charges
   → Impairments
   → Gains/losses on asset sales
   → Normalize earnings excluding one-timers
```

**Quality scoring**:
- **High (9-10/10)**: OCF > NI, FCF/NI > 90%, DSO stable, no one-timers
- **Medium (6-8/10)**: OCF ≈ NI, FCF/NI 70-90%, DSO rising slightly
- **Low (0-5/10)**: OCF < NI, FCF/NI < 70%, DSO rising significantly, frequent one-timers

---

## Template 9: Industry Positioning Analysis

**Use case**: Understand company's position relative to industry peers

**Workflow**:
```
1. get_latest_data_update_date

2. Industry Identification
   → get_stock_profile
   → Note exact industry classification

3. Profitability vs Industry (last 8 quarters)
   → get_stock_quarterly_gross_margin
   → get_industry_quarterly_gross_margin
   → Calculate spread (company - industry)
   
   → get_stock_quarterly_net_margin
   → get_industry_quarterly_net_margin
   → Calculate spread

   → get_stock_quarterly_roe
   → get_industry_quarterly_roe
   → Calculate spread

4. Valuation vs Industry (3 years)
   → get_stock_ttm_pe
   → get_industry_ttm_pe
   → Current premium/discount

   → get_stock_ps_ratio
   → get_industry_ps_ratio
   → Current premium/discount

5. Justify Valuation Premium/Discount
   If trading at premium:
   → Must have superior margins OR growth OR returns
   → get_stock_quarterly_revenue_yoy_growth
   → Compare to industry average (estimate from multiple stocks)

   If trading at discount:
   → Check for deteriorating fundamentals
   → Temporary issues or structural decline?

6. Trend Analysis
   → Is premium/discount widening or narrowing?
   → Margin spread expanding or contracting?
   → Market recognizing outperformance/underperformance?

7. DuPont vs Industry
   → get_stock_quarterly_equity_multiplier
   → get_stock_quarterly_asset_turnover
   → get_industry_quarterly_equity_multiplier
   → get_industry_quarterly_asset_turnover
   → Which component drives performance difference?
```

**Positioning profiles**:
- **Leader**: All margins > industry, P/E premium, ROE > industry
- **Challenger**: Some margins > industry, P/E at industry avg, ROE approaching industry
- **Laggard**: Margins < industry, P/E discount, ROE < industry
- **Turnaround**: Margins improving, P/E discount narrowing

---

## Template 10: Quarterly Earnings Analysis

**Use case**: Analyze latest earnings release in detail

**Workflow**:
```
1. get_latest_data_update_date

2. Identify Latest Quarter
   → get_stock_earning_call_transcripts_list
   → Note most recent fiscal_year and fiscal_quarter

3. Read Management Commentary
   → get_stock_earning_call_transcript (latest quarter)
   → Key themes, guidance, concerns
   → Management tone

4. Verify Quantitative Results
   → get_stock_quarterly_income_statement
   → Latest quarter vs year-ago quarter
   → Revenue beat/miss
   → EPS beat/miss
   → Margin trends

5. Sequential Analysis (QoQ)
   → Compare latest quarter to prior quarter
   → Seasonal business? Normal patterns?
   → Sequential improvement or deterioration?

6. Year-over-Year Analysis
   → get_stock_quarterly_revenue_yoy_growth (latest)
   → get_stock_quarterly_operating_income_yoy_growth
   → get_stock_quarterly_net_income_yoy_growth
   → Acceleration or deceleration?

7. Segment Performance
   → get_quarterly_revenue_by_segment
   → Which segments drove growth?
   → Any segments declining?

8. Balance Sheet Changes
   → get_stock_quarterly_balance_sheet (latest)
   → Debt levels
   → Cash position
   → Working capital

9. Cash Flow Generation
   → get_stock_quarterly_cash_flow (latest)
   → Operating cash flow
   → Free cash flow
   → Quality of earnings

10. Market Reaction Context
    → get_stock_news (earnings date ± 5 days)
    → get_stock_price (earnings date ± 10 days)
    → How did market react?
    → Justified by results?

11. Updated Guidance Impact
    → From transcript: any guidance changes?
    → Impact on full-year estimates
    → Valuation implications
```

**Earnings assessment**:
- **Strong beat**: Revenue +3%, EPS +5%, margin expansion, guidance raised
- **Beat**: Revenue +1-3%, EPS +2-5%, margins stable
- **Meet**: Revenue ±1%, EPS ±2%, margins stable
- **Miss**: Revenue <-1% OR EPS <-2% OR margin compression
- **Strong miss**: Revenue <-3%, EPS <-5%, guidance lowered

---

## Best Practices Across All Templates

### Data Freshness
- Always call `get_latest_data_update_date` first
- Use this date as reference for "current" or "latest"
- When user says "recent", "latest", or "current", use data cutoff date

### Date Range Selection
- **Quick check**: 4-8 quarters (1-2 years)
- **Standard analysis**: 12-16 quarters (3-4 years)
- **Long-term trends**: 20+ quarters (5+ years)
- **Valuation history**: 5-10 years for context

### Handling Truncated Data
When API returns `truncated: true`:
- Prioritize most recent data
- Make multiple calls with narrower ranges if needed
- Use annual data for longer history

### Industry Comparison
- Always compare key metrics to industry
- Explains whether outperformance is company-specific or sector-wide
- Helps assess competitive moat

### DuPont Validation
When using profitability ratios:
- Verify: ROE = ROA × Equity Multiplier
- Verify: ROE = Net Margin × Asset Turnover × Equity Multiplier
- Check for mathematical consistency

### Growth Rate Interpretation
- Revenue growing faster than GDP (3%) = above-average
- Earnings growing faster than revenue = margin expansion
- FCF growing faster than earnings = high quality
- Compare to industry growth rates

### Margin Cascade Logic
```
Revenue
- COGS = Gross Profit (→ Gross Margin)
- Operating Expenses = Operating Income (→ Operating Margin)
+ D&A = EBITDA (→ EBITDA Margin)
- Taxes & Interest = Net Income (→ Net Margin)
- Capex = Free Cash Flow (→ FCF Margin)
```

### Bank vs Non-Bank
- Check sector in profile
- If financial institution: Skip ROIC and Equity Multiplier
- Banks have different capital structures

### Segment Analysis Priority
- Revenue by segment: Identifies growth drivers
- Revenue by geography: Assesses diversification
- Combine with margin data when available

---

## Template 11: DCF (Discounted Cash Flow) Valuation Model

**Use case**: Calculate intrinsic value using discounted free cash flow projections

**Full 11-Phase Workflow**:

### Phase 1: Data Collection & Current State
```
1. get_latest_data_update_date
   → Establish reference date for analysis

2. get_stock_profile
   → Company name, business description
   → Sector and industry (affects growth expectations)
   → Note if bank/financial institution (DCF may not apply)

3. get_stock_price (last 30 days)
   → Extract latest close price → "Current Price"
   → Used for comparison vs Fair Price

4. get_stock_quarterly_cash_flow (last 4 quarters)
   → Extract: free_cash_flow for each quarter
   → Calculate: TTM FCF = Sum of last 4 quarters
   → This is the BASE for projections

5. get_stock_quarterly_income_statement (last 4 quarters)
   → Extract: total_revenue for each quarter
   → Calculate: TTM Revenue = Sum of last 4 quarters
   → Used for FCF Margin calculation
```

**Phase 1 Output Example**:
```
Symbol: TSLA
Current Price: $246.82
TTM Free Cash Flow: $4,184,800,000
TTM Revenue: $21,214,300,000
Current FCF Margin: 19.73%
```

### Phase 2: Historical Growth Analysis (Growth Estimates Foundation)
```
6. get_stock_annual_fcf_yoy_growth
   → Show last 5-10 years of FCF growth rates
   → Identify: accelerating, stable, or decelerating pattern
   → Calculate: Average FCF growth rate
   → Note years with negative FCF (risky)

7. get_stock_quarterly_revenue_yoy_growth (last 8-12 quarters)
   → Show recent revenue growth trends
   → Calculate: Average revenue growth rate
   → Assess: consistency vs volatility
```

**Phase 2 Output Example**:
```
Historical FCF Growth (Last 5 Years):
  2020: -15.3%
  2021: +48.2%
  2022: +71.5%
  2023: +22.1%
  2024: +12.8%
  → Average: +27.9% (highly volatile, trending down)

Historical Revenue Growth (Last 8 Quarters):
  Q1 2023: +24.4%
  Q2 2023: +47.2%
  Q3 2023: +18.9%
  Q4 2023: +5.3%
  Q1 2024: +3.2%
  Q2 2024: +6.5%
  Q3 2024: +4.8%
  Q4 2024: +9.4%
  → Average: +15.0% (decelerating from highs)
```

### Phase 3: Management Outlook & Business Intelligence
```
8. get_stock_earning_call_transcripts_list
   → Identify most recent earnings call
   → Note fiscal_year and fiscal_quarter

9. get_stock_earning_call_transcript (latest)
   → Extract management's forward guidance:
     - Revenue growth targets
     - Margin expansion plans
     - New product/market expectations
     - Capex plans (affects FCF)
     - Risks and headwinds mentioned
   → Pay attention to:
     - CEO's opening remarks (strategic vision)
     - CFO's guidance (quantitative targets)
     - Q&A section (analyst concerns)

10. get_stock_news (last 3-6 months, max_rows=20)
    → Recent business developments:
      - Product launches
      - Market expansions
      - Regulatory changes
      - Competitive threats
      - Management changes
    → Sentiment: positive, neutral, negative
```

**Phase 3 Output Example**:
```
Latest Earnings Call (Q4 2024):
Management Guidance:
- Targeting 20-30% vehicle delivery growth in 2025
- Expect margin improvement from cost reductions
- Cybertruck production ramping (new growth driver)
- Energy storage business accelerating (50%+ growth)
- Concerned about: raw material costs, competition

Recent News Highlights:
- New manufacturing facility announced in Mexico
- FSD (Full Self-Driving) beta expanding
- Price competition intensifying in China
- IRA tax credits supporting demand
```

### Phase 4: Growth Rate Estimates (3-Stage Model)
```
Based on Phase 2 + Phase 3 synthesis:

STAGE 1: Near-term Growth (Years 1-5)
→ Synthesize:
  - Historical growth: FCF averaged 27.9%, Revenue averaged 15.0%
  - Management guidance: 20-30% delivery growth
  - Recent trend: Growth decelerating
  - New drivers: Cybertruck, energy storage
  - Risks: Price competition, margin pressure
→ Proposed FCF Growth Rate (1-5 years): 4.83%
  (Conservative due to deceleration, competitive pressure)
→ Proposed Revenue Growth Rate (1-5 years): 5.35%
  (Slightly higher than FCF, modest margin contraction expected)

STAGE 2: Mid-term Growth (Years 6-10)
→ Apply mean reversion principle
→ Assume growth slowdown as market matures
→ Proposed FCF Growth Rate (6-10 years): 3.23%
  (50-70% of near-term rate)
→ Proposed Revenue Growth Rate (6-10 years): 4.55%

STAGE 3: Terminal Growth Rate
11. get_daily_treasury_yield
    → Extract bc10_year (10-Year Treasury yield)
    → Example: 4.26%
→ Terminal Rate = Risk-Free Rate = 4.26%
  (Long-term GDP growth assumption)
```

**Phase 4 Output Example**:
```
Growth Rate Estimates:
┌─────────────┬──────────────┬──────────────┐
│ Period      │ FCF Growth   │ Rev Growth   │
├─────────────┼──────────────┼──────────────┤
│ Years 1-5   │ 4.83%        │ 5.35%        │
│ Years 6-10  │ 3.23%        │ 4.55%        │
│ Terminal    │ 4.26%        │ 4.26%        │
└─────────────┴──────────────┴──────────────┘

Justification:
- Near-term: Conservative vs historical due to deceleration
- Mid-term: Further slowdown as market matures
- Terminal: Risk-free rate (long-term sustainable growth)
```

### Phase 5: Discount Rate (WACC)
```
12. get_stock_wacc (latest data point)
    → Extract: wacc
    → Typical range: 7-12% for most companies
    → Display components:
      - cost_of_equity
      - cost_of_debt
      - weight_of_equity
      - weight_of_debt
      - beta_5y
      - risk_free_rate
      - expected_market_return
```

**Phase 5 Output Example**:
```
Weighted Average Cost of Capital (WACC):
  WACC: 9.57%
  
  Components:
    Cost of Equity: 9.88%
    Cost of Debt: 2.87%
    Weight of Equity: 95.85%
    Weight of Debt: 4.15%
    Beta (5Y): 0.86
    Risk-Free Rate: 4.26%
    Market Return (10Y S&P 500 CAGR): 10.80%
```

### Phase 6: Free Cash Flow Projection (10-Year)
```
Using TTM FCF as base:

Year 1 FCF = TTM FCF × (1 + Near-term Growth Rate)
Year 2 FCF = Year 1 FCF × (1 + Near-term Growth Rate)
Year 3 FCF = Year 2 FCF × (1 + Near-term Growth Rate)
Year 4 FCF = Year 3 FCF × (1 + Near-term Growth Rate)
Year 5 FCF = Year 4 FCF × (1 + Near-term Growth Rate)

Year 6 FCF = Year 5 FCF × (1 + Mid-term Growth Rate)
Year 7 FCF = Year 6 FCF × (1 + Mid-term Growth Rate)
Year 8 FCF = Year 7 FCF × (1 + Mid-term Growth Rate)
Year 9 FCF = Year 8 FCF × (1 + Mid-term Growth Rate)
Year 10 FCF = Year 9 FCF × (1 + Mid-term Growth Rate)
```

**Phase 6 Output Example** (TTM FCF = $4,184,800,000, Growth 4.83%):
```
10-Year Free Cash Flow Projection:
┌──────┬──────────────────┬───────────────┐
│ Year │ Projected FCF    │ Growth Rate   │
├──────┼──────────────────┼───────────────┤
│ 2025 │ $4,386,925,832   │ 4.83%         │
│ 2026 │ $4,598,814,341   │ 4.83%         │
│ 2027 │ $4,820,937,064   │ 4.83%         │
│ 2028 │ $5,053,788,315   │ 4.83%         │
│ 2029 │ $5,297,886,280   │ 4.83%         │
│ 2030 │ $5,469,008,007   │ 3.23%         │
│ 2031 │ $5,645,656,965   │ 3.23%         │
│ 2032 │ $5,828,011,685   │ 3.23%         │
│ 2033 │ $6,016,263,666   │ 3.23%         │
└──────┴──────────────────┴───────────────┘
```

### Phase 7: Revenue Projection (for FCF Margin)
```
Using TTM Revenue as base, apply same growth logic:

Year 1 Revenue = TTM Revenue × (1 + Near-term Revenue Growth)
Year 2 Revenue = Year 1 Revenue × (1 + Near-term Revenue Growth)
... (continue through Year 10)

Then calculate:
FCF Margin (Year N) = Projected FCF (Year N) / Projected Revenue (Year N)
```

**Phase 7 Output Example** (TTM Revenue = $21,214,300,000):
```
┌──────┬──────────────────┬──────────────────┬────────────┐
│ Year │ Projected Rev    │ Projected FCF    │ FCF Margin │
├──────┼──────────────────┼──────────────────┼────────────┤
│ 2025 │ $22,349,400,000  │ $4,386,925,832   │ 19.63%     │
│ 2026 │ $23,545,000,000  │ $4,598,814,341   │ 19.53%     │
│ 2027 │ $24,805,000,000  │ $4,820,937,064   │ 19.44%     │
│ 2028 │ $26,133,000,000  │ $5,053,788,315   │ 19.34%     │
│ 2029 │ $27,532,000,000  │ $5,297,886,280   │ 19.24%     │
│ 2030 │ $28,785,000,000  │ $5,469,008,007   │ 19.00%     │
│ 2031 │ $30,095,000,000  │ $5,645,656,965   │ 18.76%     │
│ 2032 │ $31,465,000,000  │ $5,828,011,685   │ 18.52%     │
│ 2033 │ $32,898,000,000  │ $6,016,263,666   │ 18.29%     │
└──────┴──────────────────┴──────────────────┴────────────┘

→ FCF Margin declining gradually (revenue growing faster than FCF)
→ This is realistic for mature growth phase
```

### Phase 8: Present Value of Projected FCF
```
For each year, discount FCF back to present:

PV(Year N) = Projected FCF (Year N) / (1 + WACC)^N

Example with WACC = 9.57%:
PV(Year 1) = $4,386,925,832 / (1.0957)^1 = $4,003,451,219
PV(Year 2) = $4,598,814,341 / (1.0957)^2 = $3,829,512,088
... continue for all 10 years

Sum of PV(Years 1-10) = Enterprise Value from Operations
```

**Phase 8 Output Example**:
```
Present Value of 10-Year FCF:
┌──────┬──────────────────┬──────────────────┐
│ Year │ Projected FCF    │ Present Value    │
├──────┼──────────────────┼──────────────────┤
│ 2025 │ $4,386,925,832   │ $4,003,451,219   │
│ 2026 │ $4,598,814,341   │ $3,829,512,088   │
│ 2027 │ $4,820,937,064   │ $3,663,178,445   │
│ 2028 │ $5,053,788,315   │ $3,503,894,621   │
│ 2029 │ $5,297,886,280   │ $3,351,132,509   │
│ 2030 │ $5,469,008,007   │ $3,164,722,891   │
│ 2031 │ $5,645,656,965   │ $2,988,441,226   │
│ 2032 │ $5,828,011,685   │ $2,821,577,334   │
│ 2033 │ $6,016,263,666   │ $2,663,449,872   │
├──────┴──────────────────┼──────────────────┤
│ Sum (PV of 10Y FCF)    │ $29,989,360,205  │
└────────────────────────┴──────────────────┘
```

### Phase 9: Terminal Value Calculation
```
Terminal FCF = Year 10 FCF × (1 + Terminal Growth Rate)

Terminal Value = Terminal FCF / (WACC - Terminal Growth Rate)

PV of Terminal Value = Terminal Value / (1 + WACC)^10

CRITICAL CHECK: WACC must be > Terminal Rate
(Otherwise you get infinite/negative value)
```

**Phase 9 Output Example**:
```
Terminal Value Calculation:
  Year 10 FCF: $6,016,263,666
  Terminal Growth Rate: 4.26%
  Terminal FCF (Year 11): $6,272,622,967
  
  Terminal Value = $6,272,622,967 / (0.0957 - 0.0426)
                 = $6,272,622,967 / 0.0531
                 = $118,127,909,544
  
  PV of Terminal Value = $118,127,909,544 / (1.0957)^10
                       = $118,127,909,544 / 2.4834
                       = $47,561,346,329

Terminal Value represents 61.3% of Enterprise Value
(Typical range: 60-80%)
```

### Phase 10: Enterprise Value → Equity Value → Fair Price
```
13. get_stock_quarterly_balance_sheet (latest quarter)
    → Extract: cash_cash_equivalents_and_short_term_investments
    → Extract: total_debt
    → Note reporting date

14. get_stock_market_capitalization (latest date)
    → Extract: shares_outstanding (use diluted)

Calculate:
1. Enterprise Value (EV) = Sum of PV(FCF 1-10) + PV(Terminal Value)

2. Equity Value = EV + Cash & Equivalents - Total Debt

3. Fair Price per Share = Equity Value / Shares Outstanding
```

**Phase 10 Output Example**:
```
DCF Valuation Summary:

Enterprise Value Calculation:
  PV of 10-Year FCF:        $29,989,360,205
  PV of Terminal Value:     $47,561,346,329
  ─────────────────────────────────────────
  Enterprise Value (EV):    $77,550,706,534

Equity Value Adjustments:
  (+) Cash & Equivalents:    $2,470,400,000
  (-) Total Debt:            $4,324,000,000
  ─────────────────────────────────────────
  Equity Value:             $75,697,106,534

Fair Price Calculation:
  Shares Outstanding:       404,448,744 (diluted)
  Fair Price per Share:     $187.18
  
  Current Price:            $246.82
  ─────────────────────────────────────────
  Fair Price vs Current:    -24.16% (overvalued)
```

### Phase 11: Valuation Assessment & Sensitivity
```
Compare Fair Price to Current Price:

Margin of Safety = (Fair Price - Current Price) / Fair Price × 100%

Interpretation:
  MoS > +30%:  Significantly undervalued (strong buy signal)
  MoS +10% to +30%: Moderately undervalued (buy)
  MoS -10% to +10%: Fairly valued (hold)
  MoS -30% to -10%: Moderately overvalued (sell)
  MoS < -30%: Significantly overvalued (strong sell)

CRITICAL: Also perform sensitivity analysis
Test with different assumptions:
- Bull case: +2% to all growth rates
- Base case: As calculated
- Bear case: -2% to all growth rates

Check if Fair Price is highly sensitive to assumptions
```

**Phase 11 Output Example**:
```
Valuation Assessment:

Current Market Price:     $246.82
DCF Fair Price:          $187.18
Margin of Safety:        -24.16%
Recommendation:          SELL (Overvalued)

Interpretation:
- Stock trading 32% above DCF fair value
- Either: (a) Market is too optimistic, OR
          (b) Our growth assumptions are too conservative
- Given recent growth deceleration and competitive pressure,
  current valuation appears stretched

Sensitivity Analysis:
┌───────────────┬──────────────┬──────────────┬──────────────┐
│ Scenario      │ Growth Adj   │ Fair Price   │ vs Current   │
├───────────────┼──────────────┼──────────────┼──────────────┤
│ Bull Case     │ +2% growth   │ $227.45      │ -7.8%        │
│ Base Case     │ As above     │ $187.18      │ -24.2%       │
│ Bear Case     │ -2% growth   │ $152.33      │ -38.3%       │
└───────────────┴──────────────┴──────────────┴──────────────┘

Key Risks to DCF Model:
- Assumed 4.83% FCF growth may be optimistic given recent deceleration
- Terminal rate of 4.26% is high (GDP typically 2-3%)
- High sensitivity to terminal value (61% of total)
- Competitive dynamics could pressure margins further

Suggested Actions:
1. Monitor next 2-3 quarters for growth stabilization
2. Wait for valuation to mean-revert (target entry: $180-200)
3. Revisit DCF if management guidance changes materially
```

---

### DCF Model Checklist

Before finalizing DCF valuation, verify:

**✓ Data Quality Checks**:
- [ ] Called `get_latest_data_update_date` first
- [ ] TTM FCF is positive (if negative, DCF not applicable)
- [ ] TTM FCF calculated from actual quarterly data (not assumed)
- [ ] Balance sheet data is from most recent quarter
- [ ] Shares outstanding is diluted count, not basic

**✓ Growth Rate Reasonableness**:
- [ ] Near-term growth supported by historical data + management guidance
- [ ] Mid-term growth < Near-term growth (mean reversion)
- [ ] Terminal rate = Risk-free rate (10Y Treasury)
- [ ] Terminal rate < WACC (otherwise infinite value)
- [ ] Year 10 FCF is 2-5x TTM FCF (sanity check for total growth)

**✓ Calculation Accuracy**:
- [ ] Each year compounds on previous year (not simple growth from base)
- [ ] WACC extracted from API (not manually guessed)
- [ ] Present value formula applied correctly: PV = FV / (1 + r)^n
- [ ] Terminal Value formula: TV = Year 11 FCF / (WACC - Terminal Rate)
- [ ] Cash added, Debt subtracted (not reversed)

**✓ Interpretation**:
- [ ] Terminal Value is 60-80% of EV (typical range)
- [ ] FCF Margin trend is realistic (not dramatically expanding)
- [ ] Fair Price is within reasonable range of industry P/FCF multiples
- [ ] Sensitivity analysis performed (Bull/Base/Bear cases)
- [ ] Cross-validated with other valuation methods (P/E, P/S, P/B)

**✓ Final Recommendation**:
- [ ] Clearly state: Buy / Hold / Sell
- [ ] Provide target entry price if Sell/Hold
- [ ] List 3-5 key risks to DCF assumptions
- [ ] Suggest monitoring triggers (earnings, guidance, competition)

---

### Common DCF Pitfalls & How to Avoid

**Pitfall 1: Extrapolating Peak Growth**
❌ BAD: Company grew 50% last year, so I'll use 50% for years 1-5
✅ GOOD: Growth was 50%, but decelerating. Management guides 20-25%. Industry maturity suggests 15-20% sustainable. Use 18% for years 1-5.

**Pitfall 2: Terminal Rate Too High**
❌ BAD: Using 5% terminal rate (above long-term GDP growth)
✅ GOOD: Terminal rate should equal risk-free rate (10Y Treasury ~3-4%). Cannot grow faster than economy forever.

**Pitfall 3: Ignoring Capital Intensity**
❌ BAD: Projecting 30% FCF growth without considering capex needs
✅ GOOD: High growth typically requires high capex. If company needs heavy investment, FCF growth will lag revenue growth.

**Pitfall 4: Overfitting to Recent Results**
❌ BAD: Last quarter FCF was $2B, so TTM = $8B
✅ GOOD: Always sum actual last 4 quarters. Recent quarter may be anomaly.

**Pitfall 5: Not Stress-Testing**
❌ BAD: Running DCF once with base assumptions, considering it final
✅ GOOD: Test Bull (+2% growth), Base, Bear (-2% growth) cases. See how sensitive Fair Price is to assumptions.

**Pitfall 6: Ignoring Debt Quality**
❌ BAD: Subtracting only long-term debt from EV
✅ GOOD: Use total_debt (short-term + long-term). Also consider: pension obligations, lease liabilities, preferred stock.

**Pitfall 7: Using Basic Shares**
❌ BAD: Dividing Equity Value by basic shares outstanding
✅ GOOD: Always use diluted shares (accounts for options, warrants, convertibles)

**Pitfall 8: Negative FCF Base**
❌ BAD: Attempting DCF when company has negative TTM FCF
✅ GOOD: DCF only works for FCF-positive companies. For growth/unprofitable companies, use revenue multiples or wait until profitable.

**Pitfall 9: Not Validating Against Market**
❌ BAD: DCF says fair value is $500, stock trades at $100, concluding "extreme undervaluation"
✅ GOOD: If DCF is 5x market price, revisit assumptions. Either market knows something you don't, or your assumptions are too aggressive.

**Pitfall 10: Forgetting Industry Context**
❌ BAD: Applying same growth rates to all companies
✅ GOOD: 
- Tech: 15-30% near-term growth may be reasonable
- Consumer staples: 3-8% more typical
- Industrials: 5-12% range
- Compare to industry average growth rates

---

### DCF Model: Final Thoughts

**When DCF Works Best**:
- Mature, profitable companies with positive FCF
- Predictable business models (less volatility)
- Clear visibility into growth drivers
- Management with track record of execution

**When DCF Struggles**:
- Unprofitable or negative FCF companies
- Highly cyclical businesses (commodities, construction)
- Disruptive industries with uncertain futures
- Financial institutions (complex balance sheets)

**DCF as Part of Toolbox**:
DCF should be ONE input to valuation, not the only one:
1. Run DCF → Fair Price: $187
2. Check P/E vs industry → Trading at 2x industry average
3. Check P/S vs history → At 3-year highs
4. Check momentum → Revenue decelerating

Synthesis: DCF suggests overvaluation, confirmed by high P/E and P/S. Revenue deceleration adds concern. Recommendation: Sell/Avoid.

**Remember**: 
"All models are wrong, but some are useful" - George Box

DCF provides a structured framework for thinking about value. The process of building the model (researching growth drivers, understanding margins, assessing risks) is often more valuable than the final "Fair Price" number itself.