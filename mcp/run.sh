#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

source "$DIR/../.venv/bin/activate"

export PYTHONPATH="$DIR/src:$PYTHONPATH"

exec python -m defeatbeta_mcp
