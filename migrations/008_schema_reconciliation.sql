-- Migration 008: schema reconciliation
--
-- Brings the migration history in line with reality. The following tables
-- and views existed in running databases (created directly during the V4
-- SQLite->PostgreSQL migration) but were never codified as migrations.
-- A fresh install therefore got an incomplete schema and the todo feature
-- crashed immediately ("relation todo_metadata / v_todos does not exist").
--
-- Every statement is idempotent (IF NOT EXISTS / CREATE OR REPLACE), so this
-- is a no-op on databases that already have these objects and a full
-- reconstruction on a fresh one. After this migration the schema produced by
-- migrations/ matches an organically grown database exactly.
--
-- Style note: these tables use the V4 epoch-as-BIGINT convention (timestamps
-- are bigint seconds-since-epoch) rather than the TIMESTAMP style of 001.
-- Reproduced faithfully so the schema stays identical to existing installs.

-- ---------------------------------------------------------------------------
-- Todo feature: per-action todo state + the read view used for listings
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS todo_metadata (
    action_id       SERIAL PRIMARY KEY REFERENCES actions(id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'open',
    priority        TEXT DEFAULT 'normal',
    category        TEXT,
    due_date        BIGINT,
    completed_at    BIGINT,
    reopened_at     BIGINT,
    reopened_count  BIGINT DEFAULT 0,
    depends_on      TEXT,
    assigned_to     TEXT,
    tags            TEXT
);

CREATE INDEX IF NOT EXISTS idx_todo_status   ON todo_metadata (status);
CREATE INDEX IF NOT EXISTS idx_todo_priority ON todo_metadata (priority);
CREATE INDEX IF NOT EXISTS idx_todo_category ON todo_metadata (category);
CREATE INDEX IF NOT EXISTS idx_todo_due      ON todo_metadata (due_date);

-- ---------------------------------------------------------------------------
-- Markdown index: per-project cache of summarised .md files
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS md_index (
    id            SERIAL PRIMARY KEY,
    file_path     TEXT,
    project_id    BIGINT REFERENCES projects(id),
    summary       TEXT,
    content_hash  TEXT,
    last_modified BIGINT
);

-- ---------------------------------------------------------------------------
-- Tech stack: detected technologies per project
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tech_stack (
    id          SERIAL PRIMARY KEY,
    project_id  BIGINT NOT NULL REFERENCES projects(id),
    category    TEXT NOT NULL,
    technology  TEXT NOT NULL,
    confidence  DOUBLE PRECISION DEFAULT 1.0,
    last_seen   BIGINT DEFAULT (EXTRACT(epoch FROM now()))::bigint,
    metadata    TEXT,
    CONSTRAINT tech_stack_project_category_unique UNIQUE (project_id, category)
);

CREATE INDEX IF NOT EXISTS idx_tech_stack_project  ON tech_stack (project_id);
CREATE INDEX IF NOT EXISTS idx_tech_stack_category ON tech_stack (category);

-- ---------------------------------------------------------------------------
-- Conflicts: logged contradictions detected during context queries
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conflicts (
    id            SERIAL PRIMARY KEY,
    timestamp     BIGINT DEFAULT (EXTRACT(epoch FROM now()))::bigint,
    project_id    BIGINT REFERENCES projects(id),
    query         TEXT,
    conflict_type TEXT,
    message       TEXT,
    resolved      BIGINT DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_conflicts_project ON conflicts (project_id);

-- ---------------------------------------------------------------------------
-- Promptstart exclusions: per-project opt-outs for pinned items
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS promptstart_exclusions (
    id                  SERIAL PRIMARY KEY,
    project_id          INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    promptstart_item_id INTEGER NOT NULL REFERENCES pinned_items(id) ON DELETE CASCADE,
    created_at          BIGINT NOT NULL DEFAULT (EXTRACT(epoch FROM now()))::bigint,
    CONSTRAINT promptstart_exclusions_project_id_promptstart_item_id_key
        UNIQUE (project_id, promptstart_item_id)
);

CREATE INDEX IF NOT EXISTS idx_promptstart_excl_project
    ON promptstart_exclusions (project_id);

-- ---------------------------------------------------------------------------
-- Test framework: suites -> cases -> executions -> assertions, plus coverage
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS test_suites (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    project_id  BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    tags        TEXT,
    active      BIGINT DEFAULT 1,
    created_at  BIGINT DEFAULT (EXTRACT(epoch FROM now()))::bigint,
    updated_at  BIGINT DEFAULT (EXTRACT(epoch FROM now()))::bigint
);

CREATE TABLE IF NOT EXISTS test_cases (
    id                 SERIAL PRIMARY KEY,
    suite_id           BIGINT NOT NULL REFERENCES test_suites(id) ON DELETE CASCADE,
    name               TEXT NOT NULL,
    description        TEXT,
    command            TEXT NOT NULL,
    working_directory  TEXT,
    timeout            BIGINT DEFAULT 300,
    expected_exit_code BIGINT DEFAULT 0,
    tags               TEXT,
    priority           TEXT DEFAULT 'normal',
    active             BIGINT DEFAULT 1,
    created_at         BIGINT DEFAULT (EXTRACT(epoch FROM now()))::bigint,
    updated_at         BIGINT DEFAULT (EXTRACT(epoch FROM now()))::bigint
);

CREATE INDEX IF NOT EXISTS idx_test_cases_suite  ON test_cases (suite_id);
CREATE INDEX IF NOT EXISTS idx_test_cases_active ON test_cases (active);

CREATE TABLE IF NOT EXISTS test_executions (
    id                     SERIAL PRIMARY KEY,
    test_case_id           BIGINT NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    action_id              BIGINT REFERENCES actions(id) ON DELETE SET NULL,
    status                 TEXT NOT NULL,
    exit_code              BIGINT,
    duration_ms            BIGINT,
    stdout_preview         TEXT,
    stderr_preview         TEXT,
    full_output_compressed BYTEA,
    environment_snapshot   TEXT,
    executed_at            BIGINT DEFAULT (EXTRACT(epoch FROM now()))::bigint,
    executed_by            TEXT
);

CREATE INDEX IF NOT EXISTS idx_test_executions_case        ON test_executions (test_case_id);
CREATE INDEX IF NOT EXISTS idx_test_executions_status      ON test_executions (status);
CREATE INDEX IF NOT EXISTS idx_test_executions_executed_at ON test_executions (executed_at);

CREATE TABLE IF NOT EXISTS test_assertions (
    id             SERIAL PRIMARY KEY,
    test_case_id   BIGINT NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    assertion_type TEXT NOT NULL,
    expected_value TEXT NOT NULL,
    actual_value   TEXT,
    passed         BIGINT,
    execution_id   BIGINT REFERENCES test_executions(id) ON DELETE CASCADE,
    checked_at     BIGINT DEFAULT (EXTRACT(epoch FROM now()))::bigint
);

CREATE INDEX IF NOT EXISTS idx_test_assertions_case      ON test_assertions (test_case_id);
CREATE INDEX IF NOT EXISTS idx_test_assertions_execution ON test_assertions (execution_id);

CREATE TABLE IF NOT EXISTS test_coverage (
    id                  SERIAL PRIMARY KEY,
    project_id          BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    component_name      TEXT NOT NULL,
    test_count          BIGINT DEFAULT 0,
    last_tested         BIGINT,
    coverage_percentage DOUBLE PRECISION,
    metadata            TEXT
);

-- ---------------------------------------------------------------------------
-- Reconcile columns/indexes on PRE-EXISTING tables. These were added directly
-- to running databases during the V4 migration and never codified, so fresh
-- installs were missing them: `cm index` crashed ("column source_hash does not
-- exist") and semantic search had no column to query.
-- ---------------------------------------------------------------------------

-- MD-indexing: indexing.py writes these columns on `cm index`
ALTER TABLE action_metadata ADD COLUMN IF NOT EXISTS source_file TEXT;
ALTER TABLE action_metadata ADD COLUMN IF NOT EXISTS source_hash TEXT;
ALTER TABLE action_metadata ADD COLUMN IF NOT EXISTS indexed_at  BIGINT;
CREATE INDEX IF NOT EXISTS idx_source_file ON action_metadata (source_file);

-- Performance indexes present on grown DBs but missing from 001
CREATE INDEX IF NOT EXISTS idx_actions_importance ON actions (importance);
CREATE INDEX IF NOT EXISTS idx_content_hash       ON action_content (content_hash);
CREATE INDEX IF NOT EXISTS idx_snippets_md5       ON snippets (md5_hash);
CREATE INDEX IF NOT EXISTS idx_snippets_modified  ON snippets (last_modified);
CREATE INDEX IF NOT EXISTS idx_snippets_type      ON snippets (file_type);
CREATE INDEX IF NOT EXISTS idx_snippets_usage     ON snippets (usage_count);

-- Semantic search: pgvector column + HNSW index. Wrapped so an install WITHOUT
-- pgvector still succeeds - semantic search stays disabled, everything else
-- works. With the recommended pgvector image the column is created here.
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'pgvector not available - semantic search disabled (install pgvector to enable it)';
END $$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        ALTER TABLE actions ADD COLUMN IF NOT EXISTS embedding vector(384);
        CREATE INDEX IF NOT EXISTS idx_actions_embedding
            ON actions USING hnsw (embedding vector_cosine_ops);
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Column type alignment. Epoch timestamps and counters belong in BIGINT, not
-- INTEGER. 001 declared several as INTEGER (e.g. snippets.created_at INTEGER
-- with a BIGINT default) which overflows on 2038-01-19 and diverges from grown
-- databases. Widening INTEGER->BIGINT is lossless and a no-op where the column
-- is already BIGINT. The views are dropped first so a view dependency does not
-- block the type change; they are recreated at the end of this file.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_todos;
DROP VIEW IF EXISTS v_project_stats;
DROP VIEW IF EXISTS v_actions_complete;

ALTER TABLE actions         ALTER COLUMN type_id      TYPE BIGINT;
ALTER TABLE actions         ALTER COLUMN project_id   TYPE BIGINT;
ALTER TABLE actions         ALTER COLUMN tokens_used  TYPE BIGINT;
ALTER TABLE actions         ALTER COLUMN importance   TYPE BIGINT;
ALTER TABLE ai_instructions ALTER COLUMN project_id   TYPE BIGINT;
ALTER TABLE ai_instructions ALTER COLUMN usage_count  TYPE BIGINT;
ALTER TABLE ai_instructions ALTER COLUMN active       TYPE BIGINT;
ALTER TABLE ai_instructions ALTER COLUMN created_at   TYPE BIGINT;
ALTER TABLE ai_instructions ALTER COLUMN updated_at   TYPE BIGINT;
ALTER TABLE entry_relations ALTER COLUMN source_id        TYPE BIGINT;
ALTER TABLE entry_relations ALTER COLUMN target_id        TYPE BIGINT;
ALTER TABLE entry_relations ALTER COLUMN created_at       TYPE BIGINT;
ALTER TABLE entry_relations ALTER COLUMN similarity_score TYPE DOUBLE PRECISION;
ALTER TABLE snippets        ALTER COLUMN project_id    TYPE BIGINT;
ALTER TABLE snippets        ALTER COLUMN file_size     TYPE BIGINT;
ALTER TABLE snippets        ALTER COLUMN line_count    TYPE BIGINT;
ALTER TABLE snippets        ALTER COLUMN usage_count   TYPE BIGINT;
ALTER TABLE snippets        ALTER COLUMN last_modified TYPE BIGINT;
ALTER TABLE snippets        ALTER COLUMN last_used     TYPE BIGINT;
ALTER TABLE snippets        ALTER COLUMN created_at    TYPE BIGINT;

-- ---------------------------------------------------------------------------
-- Read views, recreated after the type changes above.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_todos AS
    SELECT a.id,
           a.summary,
           t.status,
           t.priority,
           t.category,
           a."timestamp" AS created_at,
           t.completed_at,
           t.reopened_count,
           t.due_date,
           t.depends_on,
           t.assigned_to,
           t.tags,
           p.name AS project
      FROM actions a
      JOIN projects p ON a.project_id = p.id
      JOIN todo_metadata t ON a.id = t.action_id
      LEFT JOIN action_content ac ON a.id = ac.action_id;

CREATE OR REPLACE VIEW v_project_stats AS
    SELECT p.name,
           p.id AS project_id,
           count(a.id) AS action_count,
           count(DISTINCT a.type_id) AS type_count,
           max(a."timestamp") AS last_activity,
           count(DISTINCT a.session_id) AS session_count,
           sum(a.tokens_used) AS total_tokens
      FROM projects p
      LEFT JOIN actions a ON p.id = a.project_id
     GROUP BY p.id, p.name;

CREATE OR REPLACE VIEW v_actions_complete AS
    SELECT a.id,
           a."timestamp",
           at.name AS type,
           p.name AS project,
           a.session_id,
           a.summary,
           a.tokens_used,
           a.importance,
           ac.content,
           am.files,
           am.keywords
      FROM actions a
      JOIN action_types at ON a.type_id = at.id
      JOIN projects p ON a.project_id = p.id
      LEFT JOIN action_content ac ON a.id = ac.action_id
      LEFT JOIN action_metadata am ON a.id = am.action_id;
