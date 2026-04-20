#!/bin/bash
# Cron wrapper for embedding worker (V5)
# Uses uv + pyproject.toml entry-point, reads DB config from ~/.context/config.yaml
# Schedule: launchd every 600s (10 min)
#
# On failure, sends a desktop notification (macOS osascript / Linux notify-send)
# so users notice the problem without tailing the log. State is also written to
# the embedding_worker_runs table (see worker.py), so `cm doctor` and
# `cm save` can detect stale workers.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG="$SCRIPT_DIR/embed.log"
FAIL_MARK="$SCRIPT_DIR/.last_notified_fail"

# Ensure uv is in PATH
export PATH="$HOME/.local/bin:$PATH"

notify() {
    local title="$1"
    local msg="$2"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        osascript -e "display notification \"$msg\" with title \"$title\"" 2>/dev/null || true
    elif command -v notify-send &> /dev/null; then
        notify-send "$title" "$msg" 2>/dev/null || true
    fi
}

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"
}

# Check uv exists
if ! command -v uv &> /dev/null; then
    log "ERROR: uv not found"
    notify "ContextWolf embedding worker" "uv not in PATH - worker cannot run"
    exit 1
fi

# Run batch embedding via entry-point (reads config from ~/.context/config.yaml)
cd "$PROJECT_DIR"
if uv run cm-embed batch >> "$LOG" 2>&1; then
    # Success - clear the fail marker so the next failure triggers a fresh notification
    rm -f "$FAIL_MARK"
    exit 0
fi

# Failure path
log "ERROR: embedding worker failed (exit $?)"

# Only notify once per distinct failure-day to avoid spamming the user
# every 10 minutes when the worker is permanently broken.
TODAY=$(date '+%Y-%m-%d')
if [ ! -f "$FAIL_MARK" ] || [ "$(cat "$FAIL_MARK" 2>/dev/null)" != "$TODAY" ]; then
    echo "$TODAY" > "$FAIL_MARK"
    notify "ContextWolf embedding worker failed" "Check cm doctor. Likely fix: uv sync --extra embeddings"
fi

exit 1
