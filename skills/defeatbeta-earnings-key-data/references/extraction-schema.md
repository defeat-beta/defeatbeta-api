# Extraction Schema

Read this reference whenever extracting transcript data. Use the fields that fit the requested output; do not force unavailable fields into a human-readable table.

## Contents

- [Record Model](#record-model)
- [Core Reported Metric Catalog](#core-reported-metric-catalog)
- [Comparison Records](#comparison-records)
- [Guidance Records](#guidance-records)
- [Ambiguity Rules](#ambiguity-rules)
- [Coverage and Missing-State Rules](#coverage-and-missing-state-rules)

## Record Model

Represent each extracted item with the following logical fields:

| Field | Allowed values or format | Rule |
|---|---|---|
| `metric_id` | Stable snake_case identifier | Use the core catalog when applicable; create a precise company-specific identifier only when needed. |
| `metric_label` | Transcript-aligned display label | Preserve company terminology. |
| `category` | `reported`, `comparison`, `guidance` | Do not combine categories in one record. |
| `guidance_type` | `formal_quarterly`, `formal_annual`, `quantified_long_term`, `operating_kpi`, `market_assumption`, `directional_outlook`, or null | Keep different kinds of forward-looking information separate. |
| `period_label` | Exact fiscal or stated period | Preserve the company's fiscal labeling. |
| `period_type` | `quarter`, `fiscal_year`, `calendar_year`, `multi_year`, `long_term`, `other` | Use `other` when management states a different horizon. |
| `basis` | `gaap`, `non_gaap`, `adjusted`, `unspecified` | Do not infer GAAP from silence. |
| `basis_source` | `explicit_metric`, `call_level_default`, `unspecified` | Cite the call-level statement when it establishes the basis. |
| `value_type` | `point`, `range`, `approximate`, `minimum`, `maximum`, `direction_only` | Preserve qualifiers and range structure. |
| `raw_value` | Exact value text | Preserve the spoken number and magnitude. |
| `value` | Number or null | Use for a point value without rescaling. |
| `lower_bound` | Number or null | Populate for a range or minimum. |
| `upper_bound` | Number or null | Populate for a range or maximum. |
| `midpoint` | Number or null | Calculate only for a bounded range and label it as derived. |
| `unit` | Transcript unit | Examples: `million`, `billion`, `%`, `bps`, `percentage_points`, `shares`, `per_share`, `per_ADS`. |
| `currency_code` | ISO 4217 code or null | Require explicit or transcript-defined currency context. |
| `currency_source` | `explicit`, `transcript_default`, `symbol_only`, `unspecified` | Keep an ambiguous symbol in `raw_value` without assigning an ISO code. |
| `comparison_type` | `yoy`, `qoq`, `sequential`, `other`, or null | Use only for an explicit comparison. |
| `direction` | `up`, `down`, `unchanged`, `mixed`, or null | Derive only from explicit comparative language. |
| `change_raw_value` | Exact change text or null | Keep change magnitude separate from the reported level. |
| `guidance_status` | Defined guidance-status value or null | Require explicit support. |
| `call_section` | `prepared_remarks`, `q_and_a`, `unknown` | Use the operator transition to identify Q&A when possible. |
| `relationship` | `new`, `clarifies`, `reaffirms`, `strengthens`, `corrects`, `supersedes`, or null | Link later statements to earlier evidence when applicable. |
| `driver_text` | Management's stated driver or empty | Paraphrase minimally and retain a source reference. |
| `speaker` | Exact returned speaker | Do not promote a name to a role without evidence. |
| `paragraph_number` | Returned integer | Use multiple references when needed. |
| `source_excerpt` | Exact transcript excerpt | Quote only the text needed to support the record. |
| `availability_status` | `available`, `not_mentioned`, `mentioned_without_value`, `not_applicable`, `ambiguous`, `incomplete_coverage` | Distinguish why a requested value is unavailable. |
| `extraction_confidence` | `high`, `medium`, `low` | Rate evidence explicitness, not management sentiment. |
| `notes` | Short clarification | Explain ambiguity, conflict, calculation, or classification. |

For machine-readable output, use `source_references` as an array of objects containing `speaker`, `paragraph_number`, and `source_excerpt` rather than flattening multiple citations.

## Core Reported Metric Catalog

Extract a metric only when it is present and relevant. Do not treat this catalog as a requirement to fabricate a complete statement.

### Income Statement and Profitability

| Metric ID | Definition |
|---|---|
| `total_revenue` | Consolidated revenue for the selected period. |
| `gross_profit` | Reported gross profit. |
| `operating_expense` | Total operating expense, not an individual component. |
| `research_and_development_expense` | R&D expense when separately reported. |
| `selling_general_and_administrative_expense` | SG&A expense when separately reported. |
| `operating_income` | Income or loss from operations. Preserve negative values. |
| `net_income` | Consolidated net income or loss. |
| `net_income_attributable_to_common` | Net income attributable to common shareholders when explicitly stated. |
| `ebitda` | EBITDA as defined by management. |
| `adjusted_ebitda` | Adjusted EBITDA as defined by management. |
| `gross_margin` | Gross margin percentage. |
| `operating_margin` | Operating income margin percentage. |
| `net_margin` | Net margin percentage when explicitly stated. |
| `basic_eps` | Basic earnings per share or ADS. Preserve the denominator. |
| `diluted_eps` | Diluted earnings per share or ADS. Preserve the denominator. |
| `diluted_weighted_average_shares` | Diluted weighted-average share or ADS count. |

### Cash Flow, Liquidity, and Capital Allocation

| Metric ID | Definition |
|---|---|
| `operating_cash_flow` | Net cash from operating activities or explicitly equivalent terminology. |
| `free_cash_flow` | Free cash flow as stated by management; do not substitute operating cash flow. |
| `capital_expenditures` | Capital expenditures or purchases of property and equipment. |
| `cash_and_cash_equivalents` | Cash and cash equivalents only. |
| `cash_and_marketable_securities` | Combined total only when management reports the combination. |
| `total_liquidity` | Liquidity measure exactly as defined by management. |
| `total_debt` | Debt total when explicitly reported. |
| `share_repurchase_executed` | Value or shares repurchased during the selected period. |
| `share_repurchase_authorization_remaining` | Remaining authorization, not period repurchase activity. |
| `dividends_paid` | Dividends paid during the selected period. |

### Company-Specific Metrics

Include material segment, unit-economics, or operating metrics when they explain financial performance. Examples include segment revenue, bookings, annual recurring revenue, subscribers, units shipped, deliveries, production, average selling price, take rate, occupancy, same-store sales, credit losses, net interest margin, and funds from operations.

Identify each metric precisely. Do not label headcount, users, units, or deliveries as financial-statement metrics.

## Comparison Records

For each completed-period comparison, capture:

- The metric and current period
- The comparison baseline and `comparison_type`
- The current level if stated
- The exact change magnitude and unit if stated
- Direction
- The explicitly linked driver, if any
- Source references for both the change and driver

Do not calculate YoY or QoQ changes from two stated values unless the user requests calculations. If calculated, label the result as analyst-derived rather than management-stated.

## Guidance Records

For each quantitative forward-looking item, capture:

- Metric and accounting basis
- Exact target period or horizon
- Point, range, threshold, or approximate value
- Currency, unit, and per-share or per-ADS denominator
- Guidance status when explicit
- Management-stated drivers or assumptions
- Source references

Assign one guidance type:

| Guidance type | Definition |
|---|---|
| `formal_quarterly` | Explicit guidance for the next or another named quarter. |
| `formal_annual` | Explicit guidance for a fiscal or calendar year. |
| `quantified_long_term` | Company financial target beyond the normal annual guidance horizon. |
| `operating_kpi` | Quantified target for units, users, bookings, capacity, or another operating metric. |
| `market_assumption` | TAM, industry growth, commodity, FX, or other external forecast. |
| `directional_outlook` | Material non-numerical expectation kept outside numerical guidance tables. |

Use these guidance-status definitions:

| Status | Definition |
|---|---|
| `initiated` | First formal guidance for the period. |
| `raised` | Both the implied level and management language support an increase. |
| `lowered` | Both the implied level and management language support a decrease. |
| `narrowed` | Range width decreases without enough evidence to classify as raised or lowered. |
| `widened` | Range width increases. |
| `maintained` | Guidance is explicitly kept unchanged. |
| `reaffirmed` | Management explicitly reaffirms prior guidance. |
| `withdrawn` | Management removes or suspends prior guidance. |
| `not_stated` | No supported status classification. |

## Ambiguity Rules

- If a metric is called "adjusted" but not explicitly "non-GAAP," use `adjusted`.
- If the call preamble establishes a default basis, apply it with `basis_source: call_level_default` unless the metric explicitly overrides it. Otherwise retain an unlabeled metric's exact label and use `unspecified` basis.
- If a range uses different units or currencies at each bound, do not calculate a midpoint.
- If guidance combines multiple periods or segments, keep the combined scope; do not allocate it.
- If a value appears to be a transcription error, report it as stated and flag it rather than silently correcting it.
- If a speaker corrects an earlier number, use the corrected number and cite both paragraphs in the note.
- If Q&A strengthens or narrows a prepared statement, keep the later value and link both records with `relationship` rather than silently replacing the earlier wording.

## Coverage and Missing-State Rules

- Mark the transcript complete only when all returned paragraph numbers have been inspected and no interface truncation remains.
- Use `mentioned_without_value` when management discusses a metric but provides only a change, direction, or qualitative description instead of the requested absolute value.
- Use `ambiguous` when a value is present but its period, sign, basis, or scope cannot be resolved.
- Use `incomplete_coverage` only when missing transcript content could contain the requested value.
- Do not convert `incomplete_coverage` into `not_mentioned`.
