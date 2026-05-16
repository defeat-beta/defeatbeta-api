# DefeatBeta Skills

Skills that enhance AI's financial analysis capabilities on top of
[defeatbeta-api-mcp](../mcp/README.md). Compatible with Claude.ai, Manus,
and other AI platforms that support skills.

## Available Skills

| Skill | Description | Example |
|---|---|---|
| ~~[defeatbeta-analyst](./defeatbeta-analyst/SKILL.md)~~ _(deprecated)_ | ~~Professional financial analysis using 60+ data endpoints. Covers fundamental analysis, DCF modeling, valuation, profitability, growth assessment, and industry benchmarking.~~ Being replaced by smaller, focused skills. | — |
| [defeatbeta-earnings-preview](./defeatbeta-earnings-preview/SKILL.md) | Pre-earnings analysis using consensus estimates, transcript guidance, key metrics, bull/base/bear scenarios, catalysts, and trading setup. | [PDD Q1 FY2026 →](./examples/defeatbeta-earnings-preview.md) |
| [defeatbeta-dcf](./defeatbeta-dcf/SKILL.md) | Generates a fully editable DCF valuation Excel — WACC, 10-year FCF projections, and fair price wired as live formulas so you can flex assumptions. | [AAPL DCF →](./examples/defeatbeta-dcf.md) |
| [defeatbeta-earnings-analysis](./defeatbeta-earnings-analysis/SKILL.md) | Sell-side style post-earnings update report — 8-12 page DOCX with beat/miss analysis, updated estimates, refreshed valuation, and rating action. Tier 1/2/3 sourced; Call-Then-Write cache keeps every cited number traceable. | [AMD Q1 FY2026 →](./examples/defeatbeta-earnings-analysis.md) |

## Examples

Walkthroughs of real skill invocations — prompts, screenshots, and tips for
flexing the outputs:

- [DCF Valuation for AAPL](./examples/defeatbeta-dcf.md) — running
  `defeatbeta-dcf` in Claude Desktop to produce a fully editable
  DCF model for Apple.
- [Earnings Preview for PDD (Q1 FY2026)](./examples/defeatbeta-earnings-preview.md)
  — running `defeatbeta-earnings-preview` to synthesize a one-page pre-earnings
  briefing with bull/base/bear scenarios and a top-5 catalyst checklist.
- [Earnings Update Report for AMD (Q1 FY2026)](./examples/defeatbeta-earnings-analysis.md)
  — running `defeatbeta-earnings-analysis` to produce a full sell-side style
  8-12 page DOCX earnings update on AMD, with beat/miss analysis, updated
  estimates, and refreshed thesis. Includes the actual generated DOCX as a
  downloadable artifact.

## Prerequisites

Configure the MCP server before using any skill — see
[../mcp/README.md](../mcp/README.md).

## Packaging

To upload to Claude Desktop / Manus / etc., zip the skill folder (the
folder itself must be the zip's root):

```bash
zip -r defeatbeta-dcf.zip defeatbeta-dcf/
```
