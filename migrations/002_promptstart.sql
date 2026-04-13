-- Migration 002: Promptstart items for session startup curation
-- Allows users to pin notes, actions, snippets, and AI instructions
-- to a per-project (or global) promptstart collection.

CREATE TABLE IF NOT EXISTS promptstart_items (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    item_type TEXT NOT NULL CHECK (item_type IN ('note', 'action', 'snippet', 'ai_instruction')),
    item_id INTEGER NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    label TEXT,
    created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT
);

-- Prevent duplicate items per promptstart context
-- COALESCE handles NULL project_id (global items) for uniqueness
CREATE UNIQUE INDEX IF NOT EXISTS idx_promptstart_unique
ON promptstart_items(COALESCE(project_id, 0), item_type, item_id);

-- Fast lookup by project
CREATE INDEX IF NOT EXISTS idx_promptstart_project
ON promptstart_items(project_id);

-- Fast ordered retrieval
CREATE INDEX IF NOT EXISTS idx_promptstart_sort
ON promptstart_items(project_id, sort_order);
