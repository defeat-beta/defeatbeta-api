# DefeatBeta Skills

This directory contains skills that enhance AI's financial analysis capabilities when used
with [defeatbeta-api-mcp](../mcp/README.md) data. Compatible with Claude.ai, Manus, and other AI platforms that support
skills.

## What are Skills?

Skills are folders containing instructions and resources that teach AI how to complete specific tasks in a repeatable
way. Each skill includes a `SKILL.md` file with YAML frontmatter and detailed guidance.

## Available Skills

| Skill                                               | Description                                                                                                                                                                  |
|-----------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [defeatbeta-analyst](./defeatbeta-analyst/SKILL.md) | Professional financial analysis using 60+ data endpoints. Covers fundamental analysis, DCF modeling, valuation, profitability, growth assessment, and industry benchmarking. |
| [defeatbeta-earnings-preview](./defeatbeta-earnings-preview/SKILL.md) | Pre-earnings analysis using consensus estimates, defeatbeta MCP transcript tools, key metrics, bull/base/bear scenarios, catalysts, and trading setup. |

## Usage

### Packaging Your Skill

1. Create a ZIP file of the skill folder, for example `defeatbeta-analyst` or `defeatbeta-earnings-preview`.
2. The ZIP should contain the skill folder as its root:

```
defeatbeta-analyst.zip
  └── defeatbeta-analyst/
      ├── SKILL.md                              # Main skill instructions
      └── references/
          ├── analysis-templates.md             # Workflow templates
          └── defeatbeta-api-reference.md       # Complete API documentation
```

## Example Prompts

Once set up, you can ask directly without any preamble:

### defeatbeta-analyst

> `/defeatbeta-analyst Analyze AMD's fundamentals`
> `/defeatbeta-analyst Show me Apple's quarterly income statement`
> `/defeatbeta-analyst Run a DCF valuation on NVDA`

### defeatbeta-earnings-preview

> `/defeatbeta-earnings-preview 阿里巴巴明天公布财报，应该关注什么`

### Use in [Claude Desktop](https://claude.ai/desktop/directory)

#### 1. Configure MCP Server

To access financial data, you need to configure the MCP server first.
See [MCP installation guide for Claude Desktop](../mcp/README.md#use-in-claude-desktop).

#### 2. Add Skill Files

Navigate to **Customize → Skills → Add → Upload a skill**

Upload the `defeatbeta-analyst.zip` file

#### 3. Create a Project with Pre-configured Instructions

To avoid specifying the skill and MCP tool in every message, create a dedicated Project:

1. Go to **Projects → New Project**
2. Open **Project Instructions** and paste the following:

```
Use the defeatbeta-analyst skill and the defeatbeta-api MCP tool for all financial analysis tasks.
```

Once set up, use the example prompts above.

---

### Use in [Manus](https://manus.im/app)

#### 1. Configure MCP Server

To access financial data, you need to configure the MCP server first.
See [MCP installation guide for Manus](../mcp/README.md#use-in-manus).

#### 2. Add Skill Files

Navigate to **Settings → Skills → Add → Upload a skill**

Upload the `defeatbeta-analyst.zip` file

#### 3. Create a Project with Pre-configured Instructions

To avoid specifying the skill and MCP tool in every message, create a dedicated Project:

1. Go to **Projects → New Project**
2. In the **Instructions (optional)** field, paste the following:

```
Use the defeatbeta-analyst skill and the defeatbeta-api MCP tool for all financial analysis tasks.
```

Once set up, use the example prompts above.
