-- Migration 002: Pinned items for session startup curation
-- Allows users to pin notes, actions, snippets, and AI instructions
-- to a per-project (or global) pinned collection.

CREATE TABLE IF NOT EXISTS pinned_items (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    item_type TEXT NOT NULL CHECK (item_type IN ('note', 'action', 'snippet', 'ai_instruction')),
    item_id INTEGER NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    label TEXT,
    created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT
);

-- Prevent duplicate items per pinned context
-- COALESCE handles NULL project_id (global items) for uniqueness
CREATE UNIQUE INDEX IF NOT EXISTS idx_pinned_unique
ON pinned_items(COALESCE(project_id, 0), item_type, item_id);

-- Fast lookup by project
CREATE INDEX IF NOT EXISTS idx_pinned_project
ON pinned_items(project_id);

-- Fast ordered retrieval
CREATE INDEX IF NOT EXISTS idx_pinned_sort
ON pinned_items(project_id, sort_order);
