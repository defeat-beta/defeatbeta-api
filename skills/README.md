# DefeatBeta Skills

Skills that enhance AI's financial analysis capabilities on top of
[defeatbeta-api-mcp](../mcp/README.md). Compatible with Claude.ai, Manus,
and other AI platforms that support skills.

## Available Skills

| Skill | Description | Example |
|---|---|---|
| [defeatbeta-analyst](./defeatbeta-analyst/SKILL.md) | Professional financial analysis using 60+ data endpoints. Covers fundamental analysis, DCF modeling, valuation, profitability, growth assessment, and industry benchmarking. | _coming soon_ |
| [defeatbeta-earnings-preview](./defeatbeta-earnings-preview/SKILL.md) | Pre-earnings analysis using consensus estimates, transcript guidance, key metrics, bull/base/bear scenarios, catalysts, and trading setup. | _coming soon_ |
| [defeatbeta-dcf](./defeatbeta-dcf/SKILL.md) | Generates a fully editable DCF valuation Excel — WACC, 10-year FCF projections, and fair price wired as live formulas so you can flex assumptions. | [AAPL DCF →](./examples/defeatbeta-dcf.md) |

## Examples

Walkthroughs of real skill invocations — prompts, screenshots, and tips for
flexing the outputs:

- [DCF Valuation for AAPL](./examples/defeatbeta-dcf.md) — running
  `defeatbeta-dcf` in Claude Desktop's cowork to produce a fully editable
  DCF model for Apple.

## Prerequisites

Configure the MCP server before using any skill — see
[../mcp/README.md](../mcp/README.md).

## Packaging

To upload to Claude Desktop / Manus / etc., zip the skill folder (the
folder itself must be the zip's root):

```bash
zip -r defeatbeta-dcf.zip defeatbeta-dcf/
```
