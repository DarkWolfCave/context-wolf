-- Migration 007: "Now" sprint backlog (cross-project shortlist)
--
-- Curated shortlist of what the user is actively working on across all
-- projects. Replaces the "everything I might do someday" mindset of
-- todos with a tight, WIP-limited list ("today" / "week" / "later").
--
-- Items may either be free-form (just a title) or reference an existing
-- entity (TODO, action, note, snippet, ai_instruction, host, service).
-- When listed, the manager joins on the referenced table so the caller
-- sees the live status of the linked entity without an extra round trip.
--
-- Anti-sumpf mechanics:
--   * WIP limits per bucket (defaults: today=7, week=20, later=50)
--   * `done` bucket is a short holding area; entries older than 24h
--     are hard-deleted lazily on the next list() call

CREATE TABLE IF NOT EXISTS now_items (
    id                  SERIAL PRIMARY KEY,
    bucket              VARCHAR(16) NOT NULL
                            CHECK (bucket IN ('today', 'week', 'later', 'done')),
    title               VARCHAR(200) NOT NULL,
    project_id          INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    linked_type         VARCHAR(32)
                            CHECK (linked_type IS NULL OR linked_type IN (
                                'todo', 'action', 'note', 'snippet',
                                'ai_instruction', 'host', 'service'
                            )),
    linked_id           INTEGER,
    position            INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMP DEFAULT NOW(),
    moved_to_bucket_at  TIMESTAMP DEFAULT NOW(),
    done_at             TIMESTAMP,
    CONSTRAINT now_items_link_pair_ck
        CHECK ((linked_type IS NULL AND linked_id IS NULL)
            OR (linked_type IS NOT NULL AND linked_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_now_items_bucket_pos
    ON now_items (bucket, position);
CREATE INDEX IF NOT EXISTS idx_now_items_link
    ON now_items (linked_type, linked_id);
CREATE INDEX IF NOT EXISTS idx_now_items_done_at
    ON now_items (done_at)
    WHERE done_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_now_items_project
    ON now_items (project_id);

-- Single-row settings table for WIP limits. The 'singleton' guard CHECK
-- keeps it from ever growing beyond one row, so callers can always
-- UPDATE WHERE id = 1.
CREATE TABLE IF NOT EXISTS now_settings (
    id              INTEGER PRIMARY KEY DEFAULT 1
                        CHECK (id = 1),
    limit_today     INTEGER NOT NULL DEFAULT 7
                        CHECK (limit_today  BETWEEN 1 AND 100),
    limit_week      INTEGER NOT NULL DEFAULT 20
                        CHECK (limit_week   BETWEEN 1 AND 100),
    limit_later     INTEGER NOT NULL DEFAULT 50
                        CHECK (limit_later  BETWEEN 1 AND 100),
    updated_at      TIMESTAMP DEFAULT NOW()
);

INSERT INTO now_settings (id) VALUES (1)
ON CONFLICT (id) DO NOTHING;
