# Earnings Call Analysis Templates

Read this reference in full after selecting Template 11, 12, or 13 in `SKILL.md`. Follow the selected template's workflow, extraction schema, rules, and Output Format. Do not replace a template-specific output with a generic earnings summary.

## Shared Corrections to the Legacy Templates

These rules override conflicting legacy wording in every template:

- Select "latest" by the latest valid `report_date`, not by array position.
- Verify and disclose transcript paragraph coverage before claiming completeness.
- Preserve every numerical range. Show both bounds and a clearly labeled derived midpoint; never replace the range with the midpoint.
- Preserve the spoken magnitude and qualifier. Do not rescale millions to billions.
- Assign an ISO currency code only when the transcript explicitly names or defines it. A standalone currency symbol is not enough.
- Keep operating cash flow and free cash flow separate.
- Keep executed repurchases separate from authorization or remaining capacity.
- Preserve exact transcript sentences in sentence-level templates.
- Do not treat a number introduced only by an analyst as management guidance unless management explicitly adopts or confirms it.

## Template 11: Extract Key Financial Data from Earnings Call

**Use case:** Extract structured current-quarter financial results plus formal next-quarter and full-fiscal-year guidance from one earnings-call transcript.

### Workflow

```text
1. Resolve the target fiscal period from the transcript list.
2. Retrieve the full transcript and verify paragraph coverage.
3. Read every paragraph, including Q&A.
4. Extract the applicable fields below with speaker and paragraph number.
5. Render the three grouped tables in the Output Format below.
```

### Extraction Schema

For every available field, record the exact spoken value, unit, currency evidence, speaker, and paragraph number. Do not fill a field from memory, arithmetic, a filing, or another source unless the user explicitly requests cross-checking.

#### Current Quarter Results

| Field | Description |
|---|---|
| `total_revenue` | Consolidated revenue for the selected quarter |
| `gaap_operating_expense` | GAAP operating expenses |
| `non_gaap_operating_expense` | Non-GAAP operating expenses |
| `gaap_operating_income` | GAAP operating income or loss |
| `non_gaap_operating_income` | Non-GAAP operating income or loss |
| `gaap_net_income` | GAAP net income or loss |
| `non_gaap_net_income` | Non-GAAP net income or loss |
| `ebitda` | EBITDA as defined by management |
| `adjusted_ebitda` | Adjusted EBITDA as defined by management |
| `operating_cash_flow` | Cash from operating activities or explicitly equivalent terminology |
| `free_cash_flow` | Free cash flow as stated by management |
| `cash_and_cash_equivalents` | Cash and cash equivalents only |
| `cash_and_marketable_securities` | Combined cash and securities total only when management reports the combination |
| `total_liquidity` | Liquidity total exactly as defined by management |
| `share_repurchase_executed` | Repurchases executed during the selected quarter |
| `share_repurchase_authorization_remaining` | Remaining authorization or capacity, kept separate from executed repurchases |
| `capex` | Capital expenditures, capital spending, or purchases of PP&E |
| `gaap_gross_margin` | GAAP gross margin |
| `non_gaap_gross_margin` | Non-GAAP gross margin |
| `gaap_operating_income_margin` | GAAP operating margin |
| `non_gaap_operating_income_margin` | Non-GAAP operating margin |
| `gaap_diluted_eps` | GAAP diluted EPS per share or ADS |
| `non_gaap_diluted_eps` | Non-GAAP diluted EPS per share or ADS |
| `company_specific_metric` | Material segment or operating metric explicitly reported by management |

#### Next Quarter Guidance

| Field | Description |
|---|---|
| `revenue_guidance_next_q` | Revenue guidance for the next named fiscal quarter |
| `gaap_gross_margin_guidance_next_q` | GAAP gross margin guidance |
| `non_gaap_gross_margin_guidance_next_q` | Non-GAAP gross margin guidance |
| `gaap_operating_income_margin_guidance_next_q` | GAAP operating margin guidance |
| `non_gaap_operating_income_margin_guidance_next_q` | Non-GAAP operating margin guidance |
| `gaap_opex_guidance_next_q` | GAAP operating expense guidance |
| `non_gaap_opex_guidance_next_q` | Non-GAAP operating expense guidance |
| `ebitda_guidance_next_q` | EBITDA guidance |
| `adjusted_ebitda_guidance_next_q` | Adjusted EBITDA guidance |
| `gaap_eps_guidance_next_q` | GAAP EPS guidance per share or ADS |
| `non_gaap_eps_guidance_next_q` | Non-GAAP EPS guidance per share or ADS |
| `capex_guidance_next_q` | Capital expenditure guidance |

#### Full Fiscal Year Guidance

| Field | Description |
|---|---|
| `revenue_guidance_full_year` | Full-fiscal-year revenue guidance |
| `gaap_eps_guidance_full_year` | Full-fiscal-year GAAP EPS guidance |
| `non_gaap_eps_guidance_full_year` | Full-fiscal-year Non-GAAP EPS guidance |
| `other_formal_guidance_full_year` | Other explicitly stated formal full-year financial guidance |

### Extraction Rules

**Values and units**

- Preserve the value exactly as spoken in a `raw_value` representation.
- Record the spoken unit, such as `trillion`, `billion`, `million`, `thousand`, `%`, `bps`, `shares`, `per_share`, or `per_ADS`.
- Preserve `approximately`, `about`, `at least`, `more than`, `less than`, and equivalent qualifiers.
- For a bounded range, retain the complete range and optionally calculate a midpoint labeled `derived midpoint`.
- Do not calculate a midpoint for one-sided thresholds or ranges with inconsistent units or currencies.

**Accounting basis**

- Keep GAAP, non-GAAP, and adjusted values separate.
- Apply a call-level default only when the transcript explicitly establishes it, and disclose that the basis came from a call-level statement.
- Use `Unspecified` when neither the metric nor the call establishes a basis.

**Missing and ambiguous fields**

- Do not create rows for fields that are not mentioned.
- If one of the three grouped tables has no qualifying rows, show a plain sentence below that table heading stating that no qualifying value was found. Do not create a placeholder table row.
- List expected core fields that are not found under `Requested but unavailable` after the tables.
- Distinguish `not mentioned`, `mentioned without value`, `ambiguous`, and `incomplete coverage`.
- If a later Q&A statement clarifies or corrects a prepared value, use the clarified value and cite both paragraphs.

### Output Format

Begin with the shared header required by `SKILL.md`, then render these three grouped tables.

**Table 1 - This Quarter Results (FY{year} Q{quarter})**

| Metric | Value | Unit | Currency | Speaker | Para# |
|---|---|---|---|---|---|
| Total Revenue | 25.7 | billion | USD | CFO | 12 |
| GAAP Gross Margin | 72.5 | % | - | CFO | 12 |
| Non-GAAP Diluted EPS | 2.31 | per_share | USD | CFO | 15 |

**Table 2 - Next Quarter Guidance**

| Metric | Value | Unit | Currency | Speaker | Para# |
|---|---|---|---|---|---|
| Revenue Guidance | 26.0-27.0; derived midpoint 26.5 | billion | USD | CEO | 34 |

**Table 3 - Full Fiscal Year Guidance**

| Metric | Value | Unit | Currency | Speaker | Para# |
|---|---|---|---|---|---|
| Revenue Guidance | 105 | billion | USD | CFO | 38 |

After the tables:

- Add `Requested but unavailable` for expected core metrics with no usable value.
- Add `Ambiguities and conflicts` when basis, currency, sign, period, or transcript wording is unclear.
- Add short exact evidence excerpts for cited rows when needed for auditability. Do not paraphrase inside quotation marks.

## Template 12: Analyze Financial Metric Changes from Earnings Call

**Use case:** Extract every exact sentence that describes a factual change in a financial or material operating metric for the selected quarter versus the prior quarter, same quarter last year, or another explicitly named completed-period baseline.

### Workflow

```text
1. Resolve the target fiscal period from the transcript list.
2. Retrieve the full transcript and verify paragraph coverage.
3. Scan every sentence in every paragraph, including Q&A.
4. Classify each comparison sentence as factual or forward-looking.
5. Keep factual completed-period changes only.
6. Sort qualifying rows by paragraph number and sentence order.
7. Render the table and summary in the Output Format below.
```

### Extraction Schema

| Field | Type | Description |
|---|---|---|
| `sentence` | string | Exact transcript sentence describing a completed-period metric change; do not paraphrase |
| `speaker` | string | Exact speaker returned by the transcript tool |
| `paragraph_number` | integer | Returned paragraph number containing the sentence |
| `is_factual` | Y / N | `Y` for an already completed change; `N` for projection, guidance, expectation, target, or forecast |
| `short_summary` | string | Short phrase summarizing the metric and change |
| `direction` | up / down / unchanged | Direction explicitly supported by the sentence |
| `reason` | string | Management-stated reason using transcript wording; blank when no reason is linked |

### Extraction Rules

**What qualifies**

- The sentence names a financial metric or material operating KPI.
- The sentence explicitly compares the selected completed period with a prior quarter, prior year, same quarter last year, sequential baseline, or another named historical baseline.
- Quantitative and qualitative directional comparisons both qualify when the baseline is explicit.

**What does not qualify**

- Forecasts, targets, expectations, outlook, or guidance.
- A metric level with no period comparison.
- A general business statement without a metric.
- A comparison calculated by the agent from two separate values unless the user explicitly requests calculated comparisons.

**Factual classification**

- Use `Y` for language such as `grew`, `declined`, `expanded`, `was flat`, or `we achieved` when it describes a completed period.
- Use `N` for `we expect`, `we anticipate`, `we target`, `guidance`, conditional language, or a future period.
- When in doubt, classify as `N` and exclude the row.

**Reason and direction**

- Use `up`, `down`, or `unchanged` only when the sentence supports that direction.
- Use a reason only when management explicitly connects it to the change in the same sentence or an immediately linked sentence in the same paragraph. Otherwise leave it blank.
- Do not convert a percentage change into a percentage-point or basis-point change.

### Output Format

**Financial Metric Changes - FY{year} Q{quarter} (Factual, QoQ/YoY)**

| # | Summary | Direction | Speaker | Para# | Sentence | Reason |
|---|---|---|---|---|---|---|
| 1 | Revenue up 12% YoY | ⬆️ up | CFO | 12 | "Our revenue grew 12% year-over-year to $25.7 billion." | Strong demand in cloud segment |
| 2 | Gross margin declined QoQ | ⬇️ down | CFO | 14 | "Gross margin came in at 71.2%, down from 73.1% last quarter." | Higher component costs |
| 3 | Operating income flat YoY | ➡️ unchanged | CEO | 18 | "Operating income was essentially flat compared to the same period last year." | |

**Direction indicators:** ⬆️ up | ⬇️ down | ➡️ unchanged

After the table, add:

- `Total changes found: N (up: X, down: Y, unchanged: Z)`
- `Key themes` with one to three bullets highlighting the most material completed-period changes

The counts must reconcile exactly with the displayed rows.

## Template 13: Analyze Financial Metric Forecasts from Earnings Call

**Use case:** Extract every exact transcript sentence containing a specific numerical forward-looking statement, including formal guidance, outlook, expectations, operating targets, market assumptions, or long-term forecasts. Infer management's attitude for each qualifying sentence.

### Workflow

```text
1. Resolve the target fiscal period from the transcript list.
2. Retrieve the full transcript and verify paragraph coverage.
3. Scan every sentence in every paragraph, including Q&A.
4. Keep sentences that are both numerical and forward-looking.
5. Classify management attitude and capture an explicitly linked reason.
6. Sort qualifying rows by paragraph number and sentence order.
7. Render the table and summary in the Output Format below.
```

### Extraction Schema

| Field | Type | Description |
|---|---|---|
| `sentence` | string | Exact numerical forward-looking transcript sentence; do not paraphrase |
| `speaker` | string | Exact speaker returned by the transcript tool |
| `paragraph_number` | integer | Returned paragraph number containing the sentence |
| `short_summary` | string | Short phrase summarizing the forecast and horizon |
| `attitude` | optimistic / pessimistic / neutral | Analytical inference from management's wording and context, not a reported fact |
| `reason` | string | Management-stated driver or reason using transcript wording; blank when none is linked |

### Extraction Rules

**What qualifies**

- The sentence contains a specific monetary value, percentage, basis-point figure, EPS value, unit count, numerical range, threshold, or dated quantitative target.
- The sentence is forward-looking through language such as `we expect`, `we anticipate`, `guidance`, `we project`, `we target`, `we are on track`, or another clearly future horizon.
- Any horizon may qualify: next quarter, full fiscal year, calendar year, multi-year target, long term, operating KPI, or market/TAM forecast.

**What does not qualify**

- Completed-period results, even when numerical.
- Vague forward-looking statements without a specific number.
- Qualitative number words such as `double-digit`, `triple-digit`, `tens of billions`, or `more than double` when the sentence contains no explicit numeral.
- Restatements of historical figures.
- Numbers introduced only by an analyst unless management explicitly adopts or confirms them.

**Attitude determination**

- `optimistic`: Management signals confidence, acceleration, improvement, upside, strong growth, or performance ahead of targets.
- `pessimistic`: Management signals pressure, contraction, deceleration, headwinds, downside, or performance below prior expectations.
- `neutral`: Matter-of-fact numerical guidance without a clear positive or negative signal, or evidence is balanced.
- When in doubt, use `neutral`.
- Treat attitude and overall tone as analytical interpretation. Do not present them as quoted facts.

**Ranges, reasons, and categories**

- Preserve both bounds and qualifiers in the exact sentence and short summary.
- Use a reason only when management explicitly links it to the forecast in the same sentence or an immediately linked sentence in the same paragraph.
- Keep formal company guidance, long-term company targets, operating KPIs, and market/TAM assumptions distinguishable in the summary or reason. Do not present TAM as company revenue guidance.

### Output Format

**Financial Metric Forecasts - FY{year} Q{quarter}**

| # | Summary | Attitude | Speaker | Para# | Sentence | Reason |
|---|---|---|---|---|---|---|
| 1 | Q2 revenue guidance $26-27B | 😊 optimistic | CEO | 34 | "We expect revenue in the range of $26 to $27 billion for the next quarter." | Continued cloud demand and strong pipeline |
| 2 | Full-year gross margin approximately 72% | 😐 neutral | CFO | 38 | "We anticipate full-year non-GAAP gross margin of approximately 72%." | |
| 3 | Q2 operating margin down approximately 200bps | 😟 pessimistic | CFO | 41 | "We expect operating margin to decline by roughly 200 basis points sequentially due to increased R&D investment." | Planned headcount additions and infrastructure spend |

**Attitude indicators:** 😊 optimistic | 😐 neutral | 😟 pessimistic

After the table, add:

- `Total forecasts found: N (optimistic: X, neutral: Y, pessimistic: Z)`
- `Overall management tone` with one sentence characterizing the dominant attitude across displayed rows
- `Key themes` with one to three bullets on the most significant numerical forecasts

The attitude counts must reconcile exactly with the displayed rows. Overall tone is an analytical summary, not a management quote.
