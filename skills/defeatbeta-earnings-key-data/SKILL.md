---
name: defeatbeta-earnings-key-data
description: "Extract traceable key financial results, explicit period-over-period changes, and numerical management guidance from public-company earnings-call transcripts through the DefeatBeta MCP tools. Use when a user asks what a company reported, requests key quarterly metrics, asks what changed QoQ or YoY, wants management guidance or outlook, or needs structured earnings-call financial data. Do not use for a full post-earnings research report, valuation, or a general transcript summary without financial-data extraction."
---

# DefeatBeta Earnings Key Data

Extract financial facts from a single earnings-call transcript without adding unsupported estimates. Keep every reported value traceable to the transcript.

## Select the Task Mode

Choose the narrowest mode that satisfies the request:

1. **Key data**: Extract reported results plus explicit management guidance. Use this as the default when the user asks broadly for key financial data.
2. **Changes**: Extract completed-period QoQ, YoY, or other explicitly stated period comparisons.
3. **Guidance**: Extract numerical forward-looking statements, guidance changes, targets, and stated drivers.
4. **Combined**: Run all three modes only when the user requests a comprehensive transcript extraction.

Do not turn a focused request into a general earnings report.

## Resolve the Company and Fiscal Period

1. Require an unambiguous public-company ticker. If a company name maps to multiple securities or share classes, ask for the ticker instead of guessing.
2. Call `get_stock_earning_call_transcripts_list(symbol)` before retrieving a transcript.
3. For an explicitly requested fiscal period, select the exact `fiscal_year` and `fiscal_quarter` returned by the list tool. Treat fiscal periods as company-defined, not calendar periods.
4. For "latest," select the entry with the latest valid `report_date`. Do not assume the first array element is the latest. If dates tie or are missing, use the highest fiscal year and quarter and disclose the fallback.
5. Call `get_stock_earning_call_transcript(symbol, fiscal_year, fiscal_quarter)` with the selected period.
6. Stop and report the gap if the transcript list is empty, the requested period is unavailable, or the returned `paragraphs` array is empty.

Use the exact tool names above when available. If the host namespaces MCP tools, identify the tools by their final function names rather than inventing aliases.

## Extract the Transcript

1. Read every returned paragraph in `paragraph_number` order. Do not rely only on keyword search or prepared remarks; include Q&A.
2. Preserve `speaker` and `paragraph_number` exactly as returned.
3. Capture the shortest exact source excerpt that supports each extracted fact. Keep quoted text in its original language.
4. Attach multiple source references when a fact or driver spans paragraphs. Never attach a reason from distant context unless management explicitly links it to the metric.
5. Classify each item by category, period, accounting basis, value shape, unit, currency, and source using [references/extraction-schema.md](references/extraction-schema.md).
6. Extract only modes requested by the user. Apply the mode-specific rules below.

### Key Data Mode

- Extract the applicable reported metrics from the core catalog.
- Extract company-specific operating metrics only when management treats them as material financial or operating drivers.
- Separate reported results from guidance even when they occur in the same sentence.
- Record metrics only for the selected earnings period unless the user requests historical comparisons.
- Mark requested metrics not found in the transcript as unavailable; do not populate them from memory, filings, financial statements, or web sources unless the user asks for cross-checking.

### Changes Mode

- Include only changes that management explicitly compares with a prior period, such as YoY, QoQ, sequential, or another named baseline.
- Require completed-period language. Exclude forecasts, targets, and hypothetical comparisons.
- Preserve both the reported level and the change when both are stated.
- Distinguish percent changes, percentage-point changes, and basis-point changes.
- Classify operating KPIs separately from financial-statement metrics.
- Extract a driver only when management explicitly states the causal relationship. Otherwise leave the driver blank.

### Guidance Mode

- Require both forward-looking context and at least one specific numerical value, range, percentage, basis-point figure, per-share amount, unit count, or dated quantitative target.
- Capture the exact horizon, such as next quarter, full fiscal year, calendar year, or long term. Never convert it to a different period.
- Classify guidance status as `initiated`, `raised`, `lowered`, `narrowed`, `widened`, `maintained`, `reaffirmed`, `withdrawn`, or `not_stated` only when supported by management's words.
- Keep a numerical range intact. Store its lower bound, upper bound, and a labeled calculated midpoint; never replace the range with the midpoint.
- Exclude vague outlook statements that contain no quantitative commitment.
- Do not infer management sentiment by default. If the user explicitly requests tone, label it as analysis, use `positive`, `negative`, `neutral`, or `mixed`, and include a confidence level.

## Apply Evidence and Normalization Rules

- Treat the transcript as the only source unless the user requests additional verification.
- Never infer a missing value from another metric. Allow arithmetic only for a clearly labeled midpoint or a user-requested calculation.
- Preserve the spoken value in `raw_value`. Do not scale millions to billions or otherwise rewrite magnitude.
- Use ISO currency codes only when the transcript explicitly names or defines the reporting currency. Do not resolve an ambiguous currency symbol from the ticker alone.
- Set accounting basis to `gaap`, `non_gaap`, `adjusted`, or `unspecified`. Never assume an unlabeled value is GAAP.
- Keep basic EPS, diluted EPS, per-share values, and per-ADS values distinct.
- Keep operating cash flow and free cash flow distinct. Do not use one as a substitute for the other.
- Record a cash total only when management states that total or clearly defines its components. Do not sum cash, investments, or securities independently.
- Keep repurchases executed during the period separate from authorized or remaining repurchase capacity.
- Preserve qualifiers such as approximately, at least, more than, and less than.
- If management states conflicting values, prefer a clearly identified correction or later update. Otherwise report both and flag the conflict.

## Present the Result

Follow [references/output-formats.md](references/output-formats.md). Match the user's language, but preserve metric identifiers, source quotes, currencies, and company terminology where translation could change meaning.

Always include:

- Company, ticker, selected fiscal period, and report date
- Scope and mode used
- Grouped results with source references
- Exact supporting excerpts
- Requested metrics not found
- Ambiguities, conflicts, incomplete tool output, or other material limitations

Omit empty optional sections. Never claim complete coverage if the tool response is truncated or paragraph numbering is discontinuous in a way that suggests missing content.

## Validate Before Responding

Check every output row against the transcript:

1. Confirm that metric, period, basis, value, unit, and currency match the source.
2. Confirm that each paragraph number and speaker exist in the returned transcript.
3. Confirm that each reported range still shows both bounds.
4. Confirm that reported results, comparisons, and guidance are not mixed.
5. Confirm that cash-flow, liquidity, repurchase, EPS, and ADS definitions remain distinct.
6. Remove duplicates that restate the same fact without adding information; retain separate sources when they resolve or qualify the fact.
7. Reconcile counts and direction summaries with the displayed rows.
8. State uncertainty instead of filling evidence gaps.
