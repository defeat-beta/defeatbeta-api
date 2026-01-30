# DefeatBeta Skills

This directory contains skills that enhance AI's financial analysis capabilities when used with [defeatbeta-api-mcp](../mcp/README.md) data. Compatible with Claude.ai, Manus, and other AI platforms that support skills.

## What are Skills?

Skills are folders containing instructions and resources that teach AI how to complete specific tasks in a repeatable way. Each skill includes a `SKILL.md` file with YAML frontmatter and detailed guidance.

## Available Skills

| Skill                                               | Description                                                                                                                                                                  |
|-----------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [defeatbeta-analyst](./defeatbeta-analyst/SKILL.md) | Professional financial analysis using 60+ data endpoints. Covers fundamental analysis, DCF modeling, valuation, profitability, growth assessment, and industry benchmarking. |

## Usage

### Packaging Your Skill
1. Create a ZIP file of the `defeatbeta-analyst` folder.
2. The ZIP should contain the `defeatbeta-analyst` folder as its root:
```
defeatbeta-analyst.zip
  └── defeatbeta-analyst/
      ├── SKILL.md
      └── references/                           # Main skill instructions
          ├── analysis-templates.md             # Workflow templates
          └── defeatbeta-api-reference.md       # Complete API documentation
```


### Use in [Claude.ai](https://claude.ai/desktop/directory)

#### 1. Configure MCP Server

To access financial data, you need to configure the MCP server first. See [MCP installation guide for Claude Desktop](../mcp/README.md#use-in-claude-desktop).

#### 2. Add Skill Files

Navigate to **Settings → Capabilities → Skills → Add → Upload a skill**

Upload the `defeatbeta-analyst.zip` file

---

### Use in [Manus](https://manus.im/app)

#### 1. Configure MCP Server

To access financial data, you need to configure the MCP server first. See [MCP installation guide for Manus](../mcp/README.md#use-in-manus).

#### 2. Add Skill Files

Navigate to **Settings → Skills → Add → Upload a skill**

Upload the `defeatbeta-analyst.zip` file
