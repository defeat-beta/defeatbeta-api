# DOCX and PDF Report Layout

Read this reference only when the user explicitly requests a Word or PDF report.

## Output Selection

- Use DOCX for an editable analyst working document.
- Use PDF for fixed-layout sharing or archival.
- When the user requests both, build both from one validated extraction dataset and keep all values, citations, and notes identical.
- Use the host's available document and PDF generation capabilities. If the host cannot create the requested format reliably, explain the limitation and provide Markdown rather than returning an unverified file.

## Recommended Length

Use two pages for a normal single-quarter extraction and no more than three pages when segment detail or long-term targets are extensive.

### Page 1: Quarter and Guidance Dashboard

- Company, ticker, fiscal period, report date, and source scope
- One-sentence factual headline without an investment recommendation
- Current-quarter reported results
- Formal next-quarter and annual guidance
- Clearly labeled derived midpoints

### Page 2: Detail and Evidence

- Segment results and material operating KPIs
- Quantified long-term outlook and market assumptions in separate sections
- Directional outlook
- Requested-but-unavailable metrics and ambiguity notes
- Evidence excerpts with speaker and paragraph number

### Optional Page 3: Evidence Appendix

Use only when the evidence excerpts do not fit legibly on page 2. Keep each excerpt paired with every metric it supports.

## Visual System

- Use a restrained research-note style with a white background, dark text, one accent color, and light table rules.
- Use landscape pages only when a table cannot remain legible in portrait orientation.
- Keep numbers right-aligned and preserve spoken magnitude, currency symbols, ranges, and qualifiers.
- Distinguish reported results, formal guidance, quantified outlook, market assumptions, and directional outlook with headings rather than decorative color alone.
- Put source markers in every data row and full excerpts in the evidence section.
- Do not add charts for a single-quarter transcript unless the user requests them or historical data is included.

## Artifact Validation

Before delivery:

1. Confirm the artifact uses the same validated records as the chat output.
2. Confirm all tables fit within page margins and no rows, headers, or citations are clipped.
3. Confirm page breaks do not separate a heading from its table or a source marker from its excerpt.
4. Confirm special characters, currency symbols, percentages, and en dashes render correctly.
5. Confirm every source paragraph exists and every quoted excerpt matches the transcript.
6. Render and visually inspect every page. Fix layout defects before delivery.
7. If both DOCX and PDF are delivered, compare the rendered pages for content parity.

## Delivery

Return a concise chat summary identifying the company, fiscal period, coverage status, and created formats. Link the finished DOCX and PDF files using their absolute paths.
