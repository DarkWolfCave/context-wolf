-- Migration 006: Embedding worker run history
-- Records each worker invocation so the CLI and GUI can detect stale or
-- broken workers without anyone having to tail a log file.
--
-- Retention is enforced by the worker itself: entries older than 30 days
-- are deleted after each successful batch (see embedding_worker/worker.py).

CREATE TABLE IF NOT EXISTS embedding_worker_runs (
    id SERIAL PRIMARY KEY,
    ran_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
    success BOOLEAN NOT NULL,
    processed_count INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER,
    error_message TEXT
);

-- Fast "most recent run" lookups (used for stale detection in cm save/context_save)
CREATE INDEX IF NOT EXISTS idx_embedding_worker_runs_ran_at
ON embedding_worker_runs(ran_at DESC);
