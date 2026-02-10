# Financial Analysis Templates

**Purpose**: Detailed, step-by-step workflow templates for executing specific financial analysis tasks.

**How to use this file**:
- Use these templates as reference guides for comprehensive analysis workflows
- Each template provides detailed API call sequences and decision criteria
- For API reference, best practices, and general guidelines, see **SKILL.md**

---

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

## Template 11: DCF (Discounted Cash Flow) Valuation

**Use case**: Calculate intrinsic value and generate comprehensive DCF valuation report

### Workflow

**Step 1: Get Data**
```
1. get_latest_data_update_date
2. get_stock_dcf_analysis(symbol)
   → Returns: discount_rate_estimates, growth_estimates, dcf_template, dcf_value, buy_sell
```

**Step 2: Validate Assumptions**
- Beta reasonableness (watch for Chinese ADRs with Beta < 0.5 - likely underestimates risk)
- Growth rates alignment with business fundamentals
- FCF margin trends (compare projected vs historical)
- Terminal Rate < WACC (must be true, otherwise invalid)

**Step 3: Cross-Validate**
- get_stock_ttm_pe / get_industry_ttm_pe (compare P/E implied by DCF vs current/industry)
- If DCF suggests 50%+ undervaluation but multiples at highs → revisit assumptions

**Step 4: Generate Professional DCF Report**

Present a comprehensive 8-section report:

#### **Section I: Valuation Conclusion**
Clear summary table with:
- Current Price
- DCF Fair Value
- Upside/Downside Potential (%)
- Investment Recommendation (Buy/Hold/Sell)
- Margin of Safety (%)

#### **Section II: Discount Rate (WACC) Analysis**
- WACC value and components table (Cost of Equity, Cost of Debt after-tax, Weights)
- Key parameters (Beta, Risk-Free Rate, Market Return, Tax Rate, Market Cap, Debt)
- WACC reasonableness commentary

#### **Section III: Historical Growth Analysis**
- 3-Year CAGR table for Revenue, FCF, EBITDA, Net Income (with weights used)
- Key observations (recovery trends, cash flow quality, efficiency improvements, profit concerns)
- 5-year FCF Margin trend table

#### **Section IV: Future Growth Assumptions**
- Growth rate framework table (Years 1-5, Years 6-10, Terminal - with rates and logic)
- Detailed growth rate calculation with weighted formula
- Reasonableness analysis vs industry/strategy/market trends

#### **Section V: 10-Year FCF Projection**
- Annual projection table (TTM baseline + Years 1-10):
  - Projected Revenue (billions)
  - Projected FCF (billions)
  - FCF Margin (%)
- Terminal Value calculation formula and result

#### **Section VI: Valuation Calculation**
- Present Value breakdown:
  - Sum of PV(Years 1-10 FCF)
  - PV(Terminal Value)
  - Enterprise Value (EV)
- Equity Value adjustment (EV + Cash - Debt)
- Fair Price per share calculation

#### **Section VII: Investment Recommendation & Risks**
- **Bull Case**: 5 specific reasons (valuation gap, cash quality, growth drivers, financial strength, competitive moats)
- **Key Risks**: 5 concrete risks (profit volatility, cyclicality, competition, regulatory, customer concentration)
- **Sensitivity Analysis**: Suggested ranges for WACC, growth rates, terminal rate, FCF margins

#### **Section VIII: Next Steps for Analysis**
- 4-6 specific follow-up analyses (investigate anomalies, verify quarterly reports, review management guidance, peer comparison, segment deep dive)

**Report formatting:**
- Use clear tables with proper alignment
- Include formulas for transparency
- Add visual indicators (✅/⚠️/⬆️/⬇️) where helpful
- Provide Excel model file path at end
- End with open-ended questions to encourage deeper exploration

---

**When DCF Works Best**:
- ✅ Mature, profitable companies with positive FCF
- ✅ Predictable business models with clear growth drivers
- ❌ Avoid for unprofitable, highly cyclical, or financial companies