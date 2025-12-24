#!/usr/bin/env bash
set -e

# Absolute path of this script
DIR="$(cd "$(dirname "$(dirname "$0")")" && pwd)"

# Activate isolated environment
source "$DIR/.venv/bin/activate"

# Start MCP server (stdio)
exec python -m defeatbeta_mcp.server
