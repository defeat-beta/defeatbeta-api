# Defeat Beta API MCP

**Defeat Beta API MCP** is an [MCP](https://modelcontextprotocol.io/introduction) server that exposes data from [defeatbeta-api](https://github.com/defeat-beta/defeatbeta-api) to large language models via standardized contextual interfaces, enabling structured and controlled financial data analysis.

Click [here](../doc/mcp/Mcp_Use_Case.md) to discover more ways to use MCP and explore additional use cases and best practices.

## Overall Architecture

```text
┌──────────────────────┐
│   MCP Client         │
│  (Cherry Studio /    │
│   Claude Desktop /   │
│   Other MCP Clients) │
└──────────┬───────────┘
           │  MCP (stdio)
           │  JSON-RPC
           ▼
┌──────────────────────────────┐
│   Defeat Beta API MCP Server │
│                              │
│  - MCP Tool Definitions      │
│  - Context Construction      │
│  - Windowing / Summarization │
│  - Output Shaping for LLM    │
│                              │
│  (runs in isolated .venv)    │
└──────────┬───────────────────┘
           │
           │  Python API Calls
           ▼
┌──────────────────────────────┐
│       defeatbeta-api         │
│  (Published PyPI Package)    │
│                              │
│  - Market Data Access        │
│  - Price / History / Metrics │
│                              │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│   Financial Data Sources     │
│   (via defeatbeta-api)       │
└──────────────────────────────┘
```

## Installation

### macOS or Linux
Run script to install:
```shell
curl -sSL https://raw.githubusercontent.com/defeat-beta/defeatbeta-api/main/mcp/install | bash
```

### What this script does

The installation script will automatically perform the following steps:

1. **Installation Location**
   * The MCP server will be installed to the local directory:
     ```text
     ~/.defeatbeta/
     ```
   * This directory contains all code and runtime resources required by the MCP server and can be safely removed to uninstall.
2. **Create an Isolated Python Virtual Environment**
   * An isolated Python virtual environment will be created at:
     ```text
     ~/.defeatbeta/.venv
     ```
   * All dependencies are installed exclusively within this environment and will not affect the system Python installation or other projects.
3. **Download and Install MCP Server Entry Scripts**
   * MCP-related files are downloaded from the `defeatbeta-api` repository.
   * The script installs and configures `mcp/run.sh` as the unified entry point for starting the MCP server.
4. **Install Runtime Dependencies**
   * Installs the MCP protocol implementation and required runtime dependencies (including `defeatbeta-api`).
   * Dependencies are resolved and installed once during installation, avoiding repeated downloads or installations at runtime.

### Installed Directory Structure

After installation, the directory structure is as follows:

```text
~/.defeatbeta/
├── .venv/                  # Isolated Python virtual environment (used by MCP Server)
│   ├── bin/
│   └── lib/
│
├── mcp/                    # MCP Server implementation
│   ├── run.sh              # MCP Server entry script (stdio mode)
│   ├── install             # Installation script (for curl | bash)
│   └── src/
│       └── defeatbeta_mcp/
│           └── server.py   # MCP Server main entry
│
└── README.md               # Local documentation
```

**Notes:**
* `run.sh`
  Serves as the single entry point to start the MCP Server, compatible with stdio-based MCP clients.
* `.venv/`
  Contains all dependencies required to run the MCP Server in an isolated environment.
* `src/defeatbeta_mcp/server.py`
  Core implementation of the MCP Server, responsible for exposing `defeatbeta-api` data as MCP tools.

## Usage

### Eg. Use in [Cherry Studio](https://www.cherry-ai.com/)


#### 1. Obtain MCP Config

After the installation is complete, the terminal will output the MCP server configuration, for example:

```text
✅ Installation completed successfully!

👉 MCP server entry:
   /Users/xxx/.defeatbeta/mcp/run.sh

👉 Studio MCP config:
--------------------------------
{
  "mcpServers": {
    "defeatbeta-api": {
      "command": "/Users/xxx/.defeatbeta/mcp/run.sh",
      "description": "An open-source alternative to Yahoo Finance's market data APIs with higher reliability.",
      "provider": "Defeat Beta API",
      "providerUrl": "https://github.com/defeat-beta/defeatbeta-api",
      "args": []
    }
  }
}
--------------------------------
```

Please record and copy the **`MCP config`** content.

---

#### 2. Import MCP Config in Cherry Studio

1. Open **Cherry Studio**.
2. Navigate to **Settings → MCP Servers**.
3. Click **+ Add Server**.
4. Paste the **`MCP config`** copied from the previous step directly into the input field.
5. Save the configuration.

Once saved, Cherry Studio will automatically start the MCP Server in **stdio mode**.

![img.png](../doc/mcp/mcp_config.png)

---

#### 3. Talk to LLM with MCP

Once the MCP Server is configured and successfully connected, you can directly ask questions to the AI in Cherry Studio, for example:

```text
- How has Tesla performed over the past month?
- Please provide me with the price of TSLA for the past 30 days.
```

The AI will use **Defeat Beta API MCP** to call the `defeatbeta-api` data interfaces, retrieve Tesla's (TSLA) market data, and provide intelligent analysis.

![img.png](../doc/mcp/talk_to_llm_with_mcp.png)
