-- Migration 003: Many-to-many scopes for pinned items
-- Allows a pinned item to be pinned to multiple projects simultaneously.
-- An item with NO rows in this table is considered global (appears everywhere).

CREATE TABLE IF NOT EXISTS pinned_item_projects (
    pinned_item_id INTEGER NOT NULL REFERENCES pinned_items(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
    PRIMARY KEY (pinned_item_id, project_id)
);

-- Fast lookup by project (for "list items in project X prompt")
CREATE INDEX IF NOT EXISTS idx_pinned_item_projects_project
ON pinned_item_projects(project_id);

-- The reverse lookup (item_id -> projects) is already served by the PK's leading column
