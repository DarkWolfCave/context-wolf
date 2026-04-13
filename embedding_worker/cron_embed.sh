#!/bin/bash
# Cron wrapper for embedding worker (V5)
# Uses uv + pyproject.toml entry-point, reads DB config from ~/.context/config.yaml
# Schedule: launchd every 600s (10 min)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG="$SCRIPT_DIR/embed.log"

# Ensure uv is in PATH
export PATH="$HOME/.local/bin:$PATH"

# Check uv exists
if ! command -v uv &> /dev/null; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') ERROR: uv not found" >> "$LOG"
    exit 1
fi

# Run batch embedding via entry-point (reads config from ~/.context/config.yaml)
cd "$PROJECT_DIR"
uv run cm-embed batch >> "$LOG" 2>&1
