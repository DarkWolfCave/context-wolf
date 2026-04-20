# Changelog

All notable changes to ContextWolf will be documented in this file.

## [5.0.4] - 2026-04-20

Embedding worker health monitoring - failures become visible without manual log-tailing.

### Added
- Migration 006: new `embedding_worker_runs` table. Every worker invocation
  records success/failure, duration, and processed count. Retention is
  30 days, trimmed by the worker itself after each successful batch.
- `cron_embed.sh` now fires a desktop notification on failure (macOS
  `osascript`, Linux `notify-send`), deduplicated to once per calendar
  day so the user notices the problem without spam.
- `cm save` and the `context_save` MCP tool emit a one-time-per-day
  warning when the worker's latest successful run is older than 48h.
  Claude Code surfaces the MCP variant to the user automatically.
- `cm doctor` reports embedding coverage percentage, last successful
  run age, and failure count from the last 24h. Stale workers show a
  clear fix command (`uv sync --extra embeddings`).

### Fixed
- The embedding worker previously failed silently when `numpy` /
  `onnxruntime` were missing (e.g., after `uv sync` without `--extra
  embeddings`). Failures now surface via notifications, DB records,
  and user-facing warnings on the next save.

### Internal
- `src/core/embedding_health.py`: shared stale-detection helper used
  by both the CLI and the MCP server. Tolerant of missing tables on
  older installs (migration 006 not applied yet).

## [5.0.3] - 2026-04-20

Pinned items (GUI feature integration) and schema hardening.

### Added
- New CLI command `cm pinned` - read-only listing of items curated in
  the optional GUI (context-wolf-ui). Output as grouped Markdown, with
  `--project` filter and `--json` output. Returns empty silently when
  GUI tables are missing.
- New optional MCP tool `pinned_list` - conditionally registered at
  server startup. Only appears in the tool schema when the pinned_items
  table exists (i.e., when the GUI is installed). Keeps the MCP schema
  lean for CLI-only installations.
- Migration 003: `pinned_item_projects` table for many-to-many project
  scopes on pinned items (an item with no scope rows is global).
- Migration 005: CHECK constraints on `ai_instructions.scope` and
  `priority` columns to enforce the canonical vocabulary at the DB level.

### Changed
- Renamed feature "Promptstart" to "Pinned" across schema, GUI, CLI,
  MCP tool, and docs. The old name collided semantically with `cm ai-prompt`
  (different feature: auto session-starter vs. curated items). Fresh
  installs use the new naming; existing installations can upgrade via
  `ALTER TABLE` (manual, no downtime, no data loss).
- Migration 002 renamed: `promptstart_items` -> `pinned_items` with
  corresponding index renames.
- All `cm init` flows updated to reflect the new naming.

### Fixed
- Migration 004: normalized `ai_instructions.priority = 'may'` rows to
  `'nice'` (CLI vocabulary), cleaning up drift from an earlier GUI
  implementation that used the RFC 2119 term.

## [5.0.2] - 2026-04-19

Dependency fix to prevent broken `cm-mcp` installs.

### Fixed
- `mcp` package moved from `[project.optional-dependencies.mcp]` to core
  `dependencies`. The `cm-mcp` entry point is always registered, so a
  plain `uv sync` (without `--extra mcp`) would otherwise uninstall
  `mcp`/`pydantic` and break the MCP server with
  `ModuleNotFoundError: No module named 'pydantic'`.

### Changed
- Install instructions in README and USER_GUIDE simplified: `uv sync`
  now installs everything needed for both CLI and MCP server. Only
  `--extra embeddings` / `--extra all` remain as opt-in extras.

## [5.0.1] - 2026-04-18

English translation, improved Docker setup, documentation, and stability fixes.

### Added
- Internationalization: all CLI and MCP output translated to English
- Animated demo GIF in README (save, duplicate detection, search, stats)
- CONTRIBUTING.md for community contributions
- CHANGELOG.md for version history
- README badges (Python, License, MCP, pgvector)
- README section: "Why not Markdown files?"
- README section: privacy and token economy details
- README section: remote database setup
- README section: architecture (two-config layout)
- `.env.example` template for Docker credentials

### Changed
- PostgreSQL upgraded to PG18 with pgvector 0.8.2
- Docker network renamed to `contextwolf-net` (reusable for optional tools)
- Docker credentials now managed via `.env` (not hardcoded in compose)
- `cm init` (Docker mode) reads `.env` for password and port, auto-creates
  `.env` if missing; keeps CLI `config.yaml` and Docker `.env` in sync
- Setup script waits for PostgreSQL healthcheck before continuing
- Setup script exits cleanly on errors instead of silent failures
- Semantic search setup integrated into main setup.sh flow
- Model size references unified across documentation (~90 MB)
- MCP server migrated to FastMCP for better tool handling
- Various documentation rewrites for clarity

### Fixed
- `cm doctor`: correct Python version check (3.12+, was 3.10+)
- `cm infra`: documented valid `--location` values (local, extern)
- Bare `except:` clauses replaced with specific exception handling
- Removed broken V2-V4 legacy tests and references
- Removed em-dashes from documentation (AI boilerplate cleanup)

### Internal
- Code cleanup: removed unused token_tracking feature
- Improved FILE_TYPE_MAP for code snippet detection
- Dependency updates

## [5.0.0] - 2026-04-03

Initial public release. Rebranded from "Context Manager" to "ContextWolf".

### Added
- Python package structure with `pyproject.toml` and `uv` support
- Interactive setup script (`setup.sh`) with database wizard and MCP configuration
- `cm doctor` diagnostics command
- Demo GIF in README
- CONTRIBUTING.md
- MIT License

### Changed
- All CLI and MCP output strings translated to English
- Clean Architecture: 4-layer structure (CLI, Features, Domain, Core)
- MCP server migrated from low-level API to FastMCP
- Duplicate detection with similarity warnings at 85%+

### Removed
- SQLite backend (PostgreSQL only)
- Legacy V2/V4 code and tests

### Technical
- 31 MCP tools with deferred loading (~356 tokens overhead)
- pgvector hybrid search (full-text + vector similarity)
- Local ONNX embeddings (all-MiniLM-L6-v2, 86MB)
- Docker-hardened PostgreSQL with pgvector

## [4.3.0] - 2026-03

### Added
- MCP tool usage tracking and analytics (`cm tool-stats`)

## [4.2.0] - 2026-02

### Added
- Universal search across all content types (`cm smart-search`)
- Advanced AI instruction search with filters

## [4.1.0] - 2026-01

### Added
- Session-aware AI prompt generation (smart mode)

## [4.0.0] - 2025-12

### Changed
- Migrated from SQLite to PostgreSQL backend
- Added pgvector for semantic search
