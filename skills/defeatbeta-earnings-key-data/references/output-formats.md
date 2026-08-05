# Output Formats

Use the default Markdown format unless the user requests JSON, CSV, or another structured representation. Keep the output compact while preserving traceability.

## Default Header

State:

- Company and ticker
- Fiscal period and report date
- Selected mode
- Source scope: earnings-call transcript only, unless additional sources were requested

## Key Data Mode

### Reported Results

| Metric | Basis | Reported value | Period | Source |
|---|---|---:|---|---|
| Total revenue | GAAP | USD 25.7 billion | FY2026 Q2 | CFO, paragraph 12 |

### Management Guidance

| Metric | Basis | Horizon | Guidance | Derived midpoint | Status | Source |
|---|---|---|---:|---:|---|---|
| Revenue | Unspecified | FY2026 Q3 | USD 26.0-27.0 billion | USD 26.5 billion | Initiated | CFO, paragraph 34 |

Display `Derived midpoint` only for bounded ranges. Preserve qualifiers such as approximately, at least, and less than in the `Guidance` column.

## Changes Mode

| Metric | Comparison | Reported level | Change | Direction | Management-stated driver | Source |
|---|---|---:|---:|---|---|---|
| Revenue | YoY | USD 25.7 billion | 12% | Up | Cloud demand | CFO, paragraph 12 |

Use separate rows when one sentence contains changes for multiple metrics. Do not show a driver unless its causal link is explicit.

After the table, provide counts only when useful:

- Total changes: N
- Up: X
- Down: Y
- Unchanged: Z
- Mixed: W

Verify that the counts equal the displayed rows.

## Guidance Mode

| Metric | Basis | Horizon | Guidance | Derived midpoint | Status | Driver or assumption | Source |
|---|---|---|---:|---:|---|---|---|
| Gross margin | Non-GAAP | FY2026 | Approximately 72% | - | Reaffirmed | Product mix | CFO, paragraph 38 |

If the user explicitly requests management tone, add `Tone` and `Tone confidence` columns. Make clear that tone is analytical interpretation rather than a reported fact.

## Evidence Excerpts

List each cited paragraph once after the result tables:

> **Paragraph 12 - CFO:** "Our revenue grew 12% year over year to $25.7 billion."

If the exact source excerpt contains multiple sentences, quote only the sentences necessary to support the extracted fact and driver. Do not paraphrase inside quotation marks.

## Missing and Ambiguous Items

Add short sections when applicable:

**Requested but not found:** List only metrics the user requested or core metrics expected by the selected mode.

**Ambiguities and conflicts:** Explain unclear basis, currency, period, transcript errors, conflicting statements, calculations, or incomplete transcript coverage.

Do not render every absent catalog metric as an empty table row.

## Machine-Readable Output

When the user requests structured output, return an object with this shape:

```json
{
  "company": "Example Corp",
  "symbol": "EXM",
  "fiscal_year": 2026,
  "fiscal_quarter": 2,
  "report_date": "2026-08-01",
  "mode": ["key_data", "guidance"],
  "records": [],
  "requested_but_not_found": [],
  "ambiguities": [],
  "limitations": []
}
```

Populate each `records` item according to `extraction-schema.md`. Use JSON `null` for unavailable optional fields. Do not omit source references from non-null records.

## No-Result Output

If no qualifying records exist, state that no explicit items matching the requested criteria were found in the selected transcript. Still identify the company, fiscal period, report date, mode, and any coverage limitation. Do not create placeholder values.
