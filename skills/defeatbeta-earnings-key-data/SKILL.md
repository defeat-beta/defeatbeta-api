---
name: defeatbeta-earnings-key-data
description: "Run one of three traceable earnings-call transcript templates through the DefeatBeta MCP tools: (1) extract current-quarter results plus next-quarter and full-year guidance, (2) extract factual QoQ or YoY financial-metric change sentences, or (3) extract numerical forward-looking forecast sentences with management-attitude analysis. Use when a user asks for key earnings-call financial data, reported metrics, period-over-period changes, management forecasts or guidance, or a DOCX/PDF artifact containing one of those outputs. Do not use for valuation, consensus beat/miss analysis, stock-price reaction, or a full post-earnings research report."
---

# DefeatBeta Earnings Key Data

Extract financial facts from one earnings-call transcript. Preserve the selected template's schema and output format instead of merging all transcript analysis into a generic report.

## Route the Request

Select the narrowest matching template:

1. **Template 11 - Extract Key Financial Data from Earnings Call**
   - Use for broad requests such as "latest earnings call," "key financial data," "what did the company report," or "results and guidance."
   - Extract current-quarter results, next-quarter guidance, and full-fiscal-year guidance.
2. **Template 12 - Analyze Financial Metric Changes from Earnings Call**
   - Use when the user asks what changed QoQ, sequentially, or YoY.
   - Extract factual completed-period comparison sentences only.
3. **Template 13 - Analyze Financial Metric Forecasts from Earnings Call**
   - Use when the user asks for forecasts, numerical outlook, targets, expectations, guidance sentences, or management attitude toward those forecasts.
   - Extract numerical forward-looking sentences and classify attitude.

If the user explicitly requests all three analyses, run the templates separately and present each template's own output. Do not combine their records into one generic table.

## Select the Output Medium

- Use Markdown by default.
- Create DOCX, PDF, or both only when the user explicitly requests a file or formal report.
- For a document artifact, read [references/report-layout.md](references/report-layout.md) and preserve the selected template's tables, summaries, and evidence.
- Keep the validated extraction identical across chat, DOCX, and PDF outputs.

## Resolve the Company and Fiscal Period

1. Require an unambiguous public-company ticker. Ask for the ticker when a company name maps to multiple securities or share classes.
2. Call `get_stock_earning_call_transcripts_list(symbol)` before retrieving a transcript.
3. For an explicitly requested period, match the exact returned `fiscal_year` and `fiscal_quarter`. Treat fiscal periods as company-defined rather than calendar-defined.
4. For "latest," select the entry with the latest valid `report_date`. Do not assume the first array element is latest. If dates tie or are missing, use the highest fiscal year and quarter and disclose the fallback.
5. Call `get_stock_earning_call_transcript(symbol, fiscal_year, fiscal_quarter)` with the selected period.
6. Stop and report the gap when the transcript list is empty, the requested period is unavailable, or the returned `paragraphs` array is empty.

## Verify Transcript Coverage

Before extraction:

1. Record the paragraph count, lowest and highest paragraph numbers, duplicate numbers, and missing numbers.
2. Detect interface truncation separately from missing transcript paragraphs.
3. If an interface truncates the response, retrieve and inspect manageable paragraph ranges until every returned paragraph has been read.
4. If complete recovery is impossible, identify every uninspected range and mark the output `incomplete`.

Never describe partial coverage as complete.

## Apply the Selected Template

Read [references/analysis-templates.md](references/analysis-templates.md) in full, then follow only the selected template's workflow, extraction schema, rules, and Output Format.

Read [references/extraction-schema.md](references/extraction-schema.md) only when the user requests JSON, CSV, another machine-readable representation, or a combined normalized dataset. The selected template remains authoritative for the human-readable output.

## Shared Evidence Rules

- Treat the selected transcript as the only source unless the user requests cross-checking.
- Read all returned paragraphs in `paragraph_number` order, including Q&A.
- Preserve `speaker` and `paragraph_number` exactly as returned.
- Preserve exact qualifying sentences for Templates 12 and 13. Do not paraphrase the `Sentence` column.
- Preserve the spoken magnitude, qualifiers, ranges, percentages, basis points, per-share or per-ADS denominator, and fiscal horizon.
- Keep every numerical range intact. Show both bounds and label any calculated midpoint as derived.
- Use an ISO currency code only when the transcript explicitly names or defines it. If the transcript uses only a currency symbol, preserve the symbol and show the currency as `-` or unspecified.
- Do not infer GAAP from silence. Use an explicit call-level basis only when the transcript establishes one.
- Keep operating cash flow and free cash flow separate.
- Do not construct a cash total by independently adding components.
- Keep executed share repurchases separate from authorization or remaining capacity.
- Treat analyst-supplied figures as questions, not management forecasts, unless management explicitly adopts or confirms the figure.
- When Q&A clarifies, strengthens, corrects, or supersedes prepared remarks, retain both references and explain the relationship.
- Report conflicts or apparent transcription errors instead of silently correcting them.

## Present the Result

Always include a short header with:

- Company and ticker
- Selected fiscal period and report date
- Selected template
- Earnings-call transcript as the source scope
- Transcript paragraph coverage and `complete` or `incomplete` status

Then render the exact Output Format defined by the selected template. Match the user's language, but keep exact transcript sentences in their original language.

## Validate Before Responding

1. Confirm complete coverage or disclose every uninspected range.
2. Confirm every displayed speaker and paragraph number exists in the transcript.
3. Confirm every sentence in Template 12 or 13 is exact transcript text.
4. Confirm Template 12 contains completed-period comparisons and excludes forecasts.
5. Confirm Template 13 contains numerical forward-looking statements and excludes analyst-only figures.
6. Confirm every range retains both bounds and any midpoint is labeled derived.
7. Confirm reasons use management-stated causal language; leave blank when no reason is stated.
8. Reconcile Template 12 direction counts or Template 13 attitude counts with the displayed rows.
9. State ambiguity instead of filling evidence gaps.
