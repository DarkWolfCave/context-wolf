# Changelog

All notable changes to ContextWolf will be documented in this file.

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
