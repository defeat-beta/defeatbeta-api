# DOCX and PDF Report Layout

Read this reference only when the user explicitly requests a DOCX or PDF artifact.

## Preserve the Selected Template

- Use DOCX for an editable analyst working document.
- Use PDF for fixed-layout sharing or archival.
- When the user requests both, build both from one validated extraction dataset.
- Preserve the selected template's exact table columns, row order, sentence text, counts, and post-table summary.
- Do not turn Template 12 or Template 13 into a generic research note.
- When all three templates are requested, render three clearly separated template sections rather than merging their records.

## Recommended Structure

Begin every artifact with:

- Company and ticker
- Fiscal period and report date
- Selected template or templates
- Earnings-call transcript as the source scope
- Transcript paragraph coverage and completeness status

Then use the selected template structure:

### Template 11

1. This Quarter Results
2. Next Quarter Guidance
3. Full Fiscal Year Guidance
4. Requested but unavailable
5. Ambiguities, conflicts, and short evidence excerpts

### Template 12

1. Financial Metric Changes table
2. Reconciled direction counts
3. Key themes
4. Coverage and ambiguity notes

### Template 13

1. Financial Metric Forecasts table
2. Reconciled attitude counts
3. Overall management tone, labeled as analysis
4. Key themes
5. Coverage and ambiguity notes

Use two pages for a normal extraction and no more than three pages when sentence-level tables or evidence are extensive. Use additional pages only when necessary to keep exact sentences legible.

## Visual System

- Use a restrained research-note style with a white background, dark text, one accent color, and light table rules.
- Use landscape pages when Template 12 or Template 13 sentence columns cannot remain legible in portrait orientation.
- Keep numeric values right-aligned where practical.
- Preserve exact currency symbols, percentages, ranges, qualifiers, and transcript sentences.
- Put the speaker and paragraph number in every data row.
- Do not add charts unless the user requests them or the artifact includes historical data beyond the selected transcript.

## Artifact Validation

Before delivery:

1. Confirm the artifact contains the same validated rows as the chat or extraction dataset.
2. Confirm the selected template's required columns are present and in the documented order.
3. Confirm all tables fit within page margins and no rows, headers, sentences, or citations are clipped.
4. Confirm page breaks do not separate a heading from its table or a source marker from its sentence.
5. Confirm every exact sentence, speaker, and paragraph number matches the transcript.
6. Confirm special characters, currency symbols, percentages, and direction or attitude indicators render correctly.
7. Confirm Template 12 direction counts or Template 13 attitude counts reconcile with displayed rows.
8. Render and visually inspect every page. Fix layout defects before delivery.
9. If both DOCX and PDF are delivered, compare the rendered outputs for content parity.

## Delivery

Return a concise chat summary identifying the company, fiscal period, template, coverage status, and created formats. Link the finished files using absolute paths.
