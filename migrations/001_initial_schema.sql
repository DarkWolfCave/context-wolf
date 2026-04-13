-- Migration 001: Initial schema (all tables as of V5.0.0)
-- This consolidates everything that setup_schema(), setup_fts(),
-- and feature-level table creation did previously.

-- ============================================================
-- Core tables
-- ============================================================

CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    path TEXT,
    created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
    last_active BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT
);

CREATE TABLE IF NOT EXISTS action_types (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

INSERT INTO action_types (name) VALUES
    ('code'), ('decision'), ('fix'), ('command'), ('docs'),
    ('general'), ('todo'), ('test'), ('feature'), ('refactor')
ON CONFLICT (name) DO NOTHING;

CREATE TABLE IF NOT EXISTS actions (
    id SERIAL PRIMARY KEY,
    timestamp BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
    type_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    summary TEXT,
    tokens_used INTEGER DEFAULT 0,
    importance INTEGER DEFAULT 5,
    metadata TEXT,
    FOREIGN KEY (type_id) REFERENCES action_types(id),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS action_content (
    action_id INTEGER PRIMARY KEY,
    content TEXT,
    content_compressed BYTEA,
    content_hash TEXT,
    FOREIGN KEY (action_id) REFERENCES actions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS action_metadata (
    action_id INTEGER PRIMARY KEY,
    files TEXT,
    keywords TEXT,
    custom TEXT,
    FOREIGN KEY (action_id) REFERENCES actions(id) ON DELETE CASCADE
);

-- ============================================================
-- Feature tables
-- ============================================================

CREATE TABLE IF NOT EXISTS snippets (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    file_path TEXT NOT NULL,
    description TEXT,
    file_type TEXT,
    file_size INTEGER,
    line_count INTEGER,
    tags TEXT,
    key_sections TEXT,
    extract TEXT,
    md5_hash TEXT,
    last_modified INTEGER,
    usage_count INTEGER DEFAULT 0,
    last_used INTEGER,
    created_at INTEGER DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
    project_id INTEGER,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS snippet_content (
    snippet_id INTEGER PRIMARY KEY,
    content TEXT,
    content_compressed BYTEA,
    FOREIGN KEY (snippet_id) REFERENCES snippets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ai_instructions (
    id SERIAL PRIMARY KEY,
    instruction TEXT NOT NULL,
    scope TEXT DEFAULT 'project',
    priority TEXT DEFAULT 'should',
    category TEXT,
    examples TEXT,
    rationale TEXT,
    project_id INTEGER,
    active INTEGER DEFAULT 1,
    created_at INTEGER DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
    updated_at INTEGER DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
    usage_count INTEGER DEFAULT 0,
    metadata TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS notes (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    tags TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS entry_relations (
    id SERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    similarity_score REAL NOT NULL,
    relation_type TEXT NOT NULL,
    created_at INTEGER DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
    FOREIGN KEY (source_id) REFERENCES actions(id),
    FOREIGN KEY (target_id) REFERENCES actions(id),
    UNIQUE(source_id, target_id)
);

-- ============================================================
-- Infrastructure tables
-- ============================================================

CREATE TABLE IF NOT EXISTS infra_hosts (
    id SERIAL PRIMARY KEY,
    hostname TEXT UNIQUE NOT NULL,
    ip TEXT,
    port INTEGER DEFAULT 22,
    "user" TEXT,
    identity_file TEXT,
    location TEXT CHECK (location IN ('local', 'extern') OR location IS NULL),
    provider TEXT,
    server_type TEXT,
    scope TEXT DEFAULT 'project' CHECK (scope IN ('global', 'project')),
    project_id INTEGER,
    tags TEXT,
    comment TEXT,
    created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
    updated_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS infra_services (
    id SERIAL PRIMARY KEY,
    host_id INTEGER NOT NULL,
    service_name TEXT NOT NULL,
    env TEXT CHECK (env IN ('prod', 'staging', 'dev', 'test') OR env IS NULL),
    app_path TEXT,
    service_type TEXT,
    deploy_method TEXT,
    health_url TEXT,
    scope TEXT DEFAULT 'project' CHECK (scope IN ('global', 'project')),
    project_id INTEGER,
    tags TEXT,
    comment TEXT,
    created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
    updated_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
    FOREIGN KEY (host_id) REFERENCES infra_hosts(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE(host_id, service_name)
);

-- ============================================================
-- Analytics tables
-- ============================================================

CREATE TABLE IF NOT EXISTS mcp_tool_usage (
    id SERIAL PRIMARY KEY,
    tool_name TEXT NOT NULL,
    session_id TEXT NOT NULL,
    timestamp BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT NOT NULL,
    duration_ms REAL,
    response_size_bytes INTEGER,
    success BOOLEAN DEFAULT TRUE,
    error TEXT,
    created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT
);

-- ============================================================
-- Indexes
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_actions_project_time ON actions(project_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_actions_type_time ON actions(type_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_actions_session ON actions(session_id);
CREATE INDEX IF NOT EXISTS idx_actions_timestamp ON actions(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_notes_project_id ON notes(project_id);
CREATE INDEX IF NOT EXISTS idx_notes_updated_at ON notes(updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_relations_source ON entry_relations(source_id);
CREATE INDEX IF NOT EXISTS idx_relations_target ON entry_relations(target_id);

CREATE INDEX IF NOT EXISTS idx_infra_hosts_scope ON infra_hosts(scope);
CREATE INDEX IF NOT EXISTS idx_infra_hosts_location ON infra_hosts(location);
CREATE INDEX IF NOT EXISTS idx_infra_hosts_project ON infra_hosts(project_id);
CREATE INDEX IF NOT EXISTS idx_infra_services_scope ON infra_services(scope);
CREATE INDEX IF NOT EXISTS idx_infra_services_env ON infra_services(env);
CREATE INDEX IF NOT EXISTS idx_infra_services_host ON infra_services(host_id);

CREATE INDEX IF NOT EXISTS idx_mcp_tool_usage_tool_name ON mcp_tool_usage(tool_name);
CREATE INDEX IF NOT EXISTS idx_mcp_tool_usage_timestamp ON mcp_tool_usage(timestamp);
CREATE INDEX IF NOT EXISTS idx_mcp_tool_usage_session ON mcp_tool_usage(session_id);
CREATE INDEX IF NOT EXISTS idx_mcp_tool_usage_success ON mcp_tool_usage(success);
CREATE INDEX IF NOT EXISTS idx_mcp_tool_usage_tool_time ON mcp_tool_usage(tool_name, timestamp);

-- ============================================================
-- Full-Text Search (tsvector)
-- ============================================================

ALTER TABLE actions ADD COLUMN IF NOT EXISTS search_vector tsvector;
CREATE INDEX IF NOT EXISTS actions_search_idx ON actions USING GIN(search_vector);

CREATE OR REPLACE FUNCTION actions_search_trigger() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', coalesce(NEW.summary, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(NEW.metadata, '')), 'B');
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS actions_search_update ON actions;
CREATE TRIGGER actions_search_update
BEFORE INSERT OR UPDATE ON actions
FOR EACH ROW EXECUTE FUNCTION actions_search_trigger();

UPDATE actions SET search_vector =
    setweight(to_tsvector('english', coalesce(summary, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(metadata, '')), 'B')
WHERE search_vector IS NULL;

-- Snippets FTS
ALTER TABLE snippets ADD COLUMN IF NOT EXISTS search_vector tsvector;
CREATE INDEX IF NOT EXISTS snippets_search_idx ON snippets USING GIN(search_vector);

CREATE OR REPLACE FUNCTION snippets_search_trigger() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('english',
        coalesce(NEW.name, '') || ' ' ||
        coalesce(NEW.description, '') || ' ' ||
        coalesce(NEW.tags, '')
    );
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS snippets_search_update ON snippets;
CREATE TRIGGER snippets_search_update
BEFORE INSERT OR UPDATE ON snippets
FOR EACH ROW EXECUTE FUNCTION snippets_search_trigger();

-- AI Instructions FTS
ALTER TABLE ai_instructions ADD COLUMN IF NOT EXISTS search_vector tsvector;
CREATE INDEX IF NOT EXISTS ai_instructions_search_idx ON ai_instructions USING GIN(search_vector);

CREATE OR REPLACE FUNCTION ai_instructions_search_trigger() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('english',
        coalesce(NEW.instruction, '') || ' ' ||
        coalesce(NEW.category, '')
    );
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS ai_instructions_search_update ON ai_instructions;
CREATE TRIGGER ai_instructions_search_update
BEFORE INSERT OR UPDATE ON ai_instructions
FOR EACH ROW EXECUTE FUNCTION ai_instructions_search_trigger();
