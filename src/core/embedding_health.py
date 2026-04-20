"""
Embedding worker health check - stale detection for CLI and MCP.

The embedding worker writes a row to `embedding_worker_runs` on every
invocation. If the latest successful run is too old (default 48h), the
worker is considered stale - either it failed repeatedly, was never
installed, or the host was offline for a long time.

This module is deliberately tolerant: if the table is missing (old
install without migration 006), stale-detection silently returns
healthy=True and no warning is emitted. The user sees nothing unusual.
"""

from pathlib import Path
from typing import Optional
import time

# How old the latest successful run may be before we consider the
# worker stale and warn the user.
STALE_AFTER_HOURS = 48

# File marker to dedupe warnings: we warn at most once per calendar day
# to avoid spamming on every cm save / context_save call.
_WARN_DEDUP_FILE = Path.home() / ".context" / ".embedding_worker_stale_warned"


def check_stale(db) -> Optional[str]:
    """Return a human-readable warning string if the worker looks stale.

    Returns None when healthy or when stale-detection cannot determine
    the state (missing table, DB errors). Never raises.
    """
    try:
        row = db.fetchone("""
            SELECT EXTRACT(EPOCH FROM NOW())::BIGINT - MAX(ran_at) AS seconds_since
            FROM embedding_worker_runs
            WHERE success = true
        """)
    except Exception:
        # Table probably missing - treat as healthy for legacy installs
        return None

    if not row or row.get("seconds_since") is None:
        # No successful run ever recorded. Could be a fresh install
        # where the worker has never completed a batch yet. We don't
        # scream about that.
        return None

    seconds_since = row["seconds_since"]
    if seconds_since < STALE_AFTER_HOURS * 3600:
        return None

    hours = seconds_since // 3600
    return (
        f"Embedding worker last ran {hours}h ago. "
        "Semantic search quality degrades over time without fresh embeddings. "
        "Run: cm doctor"
    )


def check_and_mark_warned(db) -> Optional[str]:
    """Like check_stale() but returns the warning only once per day.

    Use this in hot paths (cm save, context_save) so the user sees the
    warning at most once per day, not on every single write.
    """
    warning = check_stale(db)
    if not warning:
        return None

    today = time.strftime("%Y-%m-%d")

    try:
        already_warned = _WARN_DEDUP_FILE.exists() and _WARN_DEDUP_FILE.read_text().strip() == today
    except Exception:
        already_warned = False

    if already_warned:
        return None

    try:
        _WARN_DEDUP_FILE.parent.mkdir(parents=True, exist_ok=True)
        _WARN_DEDUP_FILE.write_text(today)
    except Exception:
        # Best effort - warn anyway, just without the dedup
        pass

    return warning
