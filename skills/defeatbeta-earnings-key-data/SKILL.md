---
name: defeatbeta-earnings-key-data
description: "Extract traceable key financial results, explicit period-over-period changes, numerical management guidance, and material directional outlook from public-company earnings-call transcripts through the DefeatBeta MCP tools. Use when a user asks what a company reported, requests key quarterly metrics, asks what changed QoQ or YoY, wants management guidance or outlook, needs structured earnings-call financial data, or requests that extraction as a DOCX or PDF. Do not use for a full post-earnings research report, valuation, consensus beat/miss analysis, stock-price reaction, or a general transcript summary without financial-data extraction."
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

## Select the Output

- Use concise Markdown by default.
- Create DOCX, PDF, or both only when the user explicitly requests a file or a formal report.
- When creating a document artifact, read [references/report-layout.md](references/report-layout.md) and follow the host's available document-generation workflow.
- Keep the extraction dataset identical across Markdown, DOCX, and PDF outputs. Do not introduce new analysis during formatting.

## Resolve the Company and Fiscal Period

1. Require an unambiguous public-company ticker. If a company name maps to multiple securities or share classes, ask for the ticker instead of guessing.
2. Call `get_stock_earning_call_transcripts_list(symbol)` before retrieving a transcript.
3. For an explicitly requested fiscal period, select the exact `fiscal_year` and `fiscal_quarter` returned by the list tool. Treat fiscal periods as company-defined, not calendar periods.
4. For "latest," select the entry with the latest valid `report_date`. Do not assume the first array element is the latest. If dates tie or are missing, use the highest fiscal year and quarter and disclose the fallback.
5. Call `get_stock_earning_call_transcript(symbol, fiscal_year, fiscal_quarter)` with the selected period.
6. Stop and report the gap if the transcript list is empty, the requested period is unavailable, or the returned `paragraphs` array is empty.

After retrieval, verify transcript coverage before extraction:

1. Record the returned paragraph count, lowest and highest paragraph numbers, duplicate numbers, and missing numbers.
2. Detect host or interface truncation separately from gaps in the underlying transcript.
3. If output is truncated, retrieve the transcript again and isolate manageable paragraph ranges using native pagination, range parameters, or response filtering when the host supports them. Continue until every returned paragraph has been inspected.
4. If complete recovery is impossible, identify the uninspected paragraph ranges and mark the result `incomplete`. Never describe partial coverage as complete.

Use the exact tool names above when available. If the host namespaces MCP tools, identify the tools by their final function names rather than inventing aliases.

## Extract the Transcript

1. Read every returned paragraph in `paragraph_number` order. Do not rely only on keyword search or prepared remarks; include Q&A.
2. Preserve `speaker` and `paragraph_number` exactly as returned.
3. Capture the shortest exact source excerpt that supports each extracted fact. Keep quoted text in its original language.
4. Attach multiple source references when a fact or driver spans paragraphs. Never attach a reason from distant context unless management explicitly links it to the metric.
5. Classify each item by category, guidance type, period, call section, accounting basis, basis evidence, value shape, unit, currency evidence, relationship to earlier statements, availability status, and source using [references/extraction-schema.md](references/extraction-schema.md).
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

- Separate formal quarterly or annual guidance from quantified long-term outlook, operating KPI targets, market assumptions, and qualitative directional outlook.
- For numerical guidance, require both forward-looking context and at least one specific numerical value, range, percentage, basis-point figure, per-share amount, unit count, or dated quantitative target.
- Capture the exact horizon, such as next quarter, full fiscal year, calendar year, or long term. Never convert it to a different period.
- Classify guidance status as `initiated`, `raised`, `lowered`, `narrowed`, `widened`, `maintained`, `reaffirmed`, `withdrawn`, or `not_stated` only when supported by management's words.
- Keep a numerical range intact. Store its lower bound, upper bound, and a labeled calculated midpoint; never replace the range with the midpoint.
- Put material non-numerical expectations in a separate `Directional Outlook` section. Never mix them into a numerical guidance table or calculate values from phrases such as "double digit," "better than market," or "below revenue growth."
- Treat market-size and TAM forecasts as market assumptions, not company financial guidance.
- Do not infer management sentiment by default. If the user explicitly requests tone, label it as analysis, use `positive`, `negative`, `neutral`, or `mixed`, and include a confidence level.

## Apply Evidence and Normalization Rules

- Treat the transcript as the only source unless the user requests additional verification.
- Never infer a missing value from another metric. Allow arithmetic only for a clearly labeled midpoint or a user-requested calculation.
- Preserve the spoken value in `raw_value`. Do not scale millions to billions or otherwise rewrite magnitude.
- Use ISO currency codes only when the transcript explicitly names or defines the reporting currency. Preserve an ambiguous currency symbol in `raw_value`, set `currency_code` to null, and set `currency_source` to `symbol_only`.
- Set accounting basis to `gaap`, `non_gaap`, `adjusted`, or `unspecified`. Record whether the basis is explicit for the metric, established by a call-level default, or unspecified. Never assume an unlabeled value is GAAP.
- Keep basic EPS, diluted EPS, per-share values, and per-ADS values distinct.
- Keep operating cash flow and free cash flow distinct. Do not use one as a substitute for the other.
- Record a cash total only when management states that total or clearly defines its components. Do not sum cash, investments, or securities independently.
- Keep repurchases executed during the period separate from authorized or remaining repurchase capacity.
- Preserve qualifiers such as approximately, at least, more than, and less than.
- Identify whether evidence comes from prepared remarks or Q&A. When Q&A clarifies, strengthens, corrects, or supersedes an earlier statement, retain both references and record the relationship.
- If management states conflicting values, prefer a clearly identified correction or later update. Otherwise report both and flag the conflict.

## Present the Result

Follow [references/output-formats.md](references/output-formats.md). Match the user's language, but preserve metric identifiers, source quotes, currencies, and company terminology where translation could change meaning.

Always include:

- Company, ticker, selected fiscal period, and report date
- Scope and mode used
- Transcript coverage status and any uninspected ranges
- Grouped results with source references
- Exact supporting excerpts
- Requested metrics not found, mentioned without a usable value, ambiguous, or unavailable because of incomplete coverage
- Ambiguities, conflicts, incomplete tool output, or other material limitations

Omit empty optional sections. Never claim complete coverage if the tool response is truncated or paragraph numbering is discontinuous in a way that suggests missing content.

## Validate Before Responding

Check every output row against the transcript:

1. Confirm that transcript paragraph coverage is complete or explicitly marked incomplete.
2. Confirm that metric, period, guidance type, basis, basis source, value, unit, and currency evidence match the source.
3. Confirm that each paragraph number and speaker exist in the returned transcript.
4. Confirm that each reported range still shows both bounds.
5. Confirm that reported results, formal guidance, quantified outlook, market assumptions, and directional outlook are not mixed.
6. Confirm that later Q&A clarifications are linked to the statements they refine.
7. Confirm that cash-flow, liquidity, repurchase, EPS, and ADS definitions remain distinct.
8. Remove duplicates that restate the same fact without adding information; retain separate sources when they resolve or qualify the fact.
9. Reconcile counts and direction summaries with the displayed rows.
10. State uncertainty instead of filling evidence gaps.
