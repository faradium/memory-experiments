#!/bin/bash
set -u
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
set -a; . ./.env; set +a
mkdir -p results/realworld logs
uv run python realworld/run_tinydb.py
echo "TINYDB_RUN_DONE"
