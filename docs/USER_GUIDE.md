# ContextWolf User Guide

## What is ContextWolf?

Claude Code has built-in persistence - `CLAUDE.md` for project instructions, auto-memory in `MEMORY.md`, and feedback rules. These work well for small projects. But they don't scale: memory is capped at 200 lines, there's no semantic search, no cross-project queries, and no structured data (types, priorities, timestamps).

ContextWolf fills that gap. It's a local knowledge management system that stores your decisions, code patterns, infrastructure details, and TODOs in a PostgreSQL database. It connects to Claude Code via MCP (Model Context Protocol), giving Claude access to 31 tools for saving and retrieving structured knowledge - with full-text search, semantic vector search, and cross-project queries.

**Example:** You decide to use session cookies over JWTs. ContextWolf stores this as a typed decision. Two weeks later, Claude starts a fresh session and searches ContextWolf before building a login route - it finds your decision across 7,000+ entries in under 1ms, without you repeating yourself.

Everything runs locally. Your data stays on your infrastructure.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.12+ | Required |
| PostgreSQL | 13+ with [pgvector](https://github.com/pgvector/pgvector) | Docker recommended |
| uv | latest | Python package manager (installed automatically by setup) |
| Claude Code | latest | Anthropic's CLI for Claude |

---

## Quick Start

```bash
git clone https://github.com/DarkWolfCave/context-wolf.git
cd context-wolf
bash setup.sh
```

The setup script runs 5 steps:
1. Installs **uv** (if not present) and all dependencies
2. Walks you through **database configuration** (Docker or external PostgreSQL)
3. Configures **Claude Code MCP integration**
4. Optionally sets up **Semantic Search** (ONNX embeddings, ~90 MB)
5. Runs **diagnostics** to verify everything works

After setup completes, restart Claude Code. ContextWolf tools are available in every new session.

---

## Manual Setup

For those who prefer step-by-step control:

```bash
# 1. Install dependencies
uv sync --extra all            # All features (embeddings + dev)
# Or pick what you need:
# uv sync                      # Core CLI + MCP server
# uv sync --extra embeddings   # + Semantic search

# 2. Start PostgreSQL
cp .env.example .env
# Edit .env and set POSTGRES_PASSWORD
docker compose up -d

# 3. Configure CLI (reads .env, writes ~/.context/config.yaml)
cm init

# 4. Register MCP server with Claude Code
cm setup-mcp

# 5. Verify installation
cm doctor
```

### Database via Docker

```bash
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD, optionally change POSTGRES_PORT
docker compose up -d
```

This starts PostgreSQL with pgvector on the port configured in `.env` (default 5432). Data is stored in `./data/postgres/` (bind mount, gitignored). The `cm init` wizard reads the same `.env` so CLI and Docker use identical credentials.

For PostgreSQL on a separate server (NAS, Raspberry Pi), see the [README](../README.md#database-on-a-separate-server).

---

## First Steps

Once installed, try these commands to get familiar:

```bash
# Save your first context entry
cm save "Project uses PostgreSQL with pgvector for storage"

# Search for it
cm search "database"

# View today's session activity
cm session

# Check system health
cm doctor

# See database statistics
cm stats
```

In Claude Code, you can also ask Claude directly:

> "Save this decision: we use Tailwind CSS, no custom CSS."

Claude will call `context_save` automatically via MCP.

---

## Key Concepts

### Projects

Every context entry belongs to a project. ContextWolf auto-detects the current project from your working directory. You can search within one project or across all projects.

### Sessions

A session groups all activity for a day. Use `cm session` or the `session()` MCP tool to see what happened today.

### Context Entries

The core data unit. Each entry has:
- **Content** - What you want to remember
- **Type** - `code`, `fix`, `feature`, `decision`, `refactor`, `test`, `doc`, `command`
- **Project** - Which project it belongs to
- **Tags** - Optional labels for filtering
- **Timestamp** - When it was saved

### Duplicate Detection

When saving, ContextWolf checks for entries with 85%+ similarity and warns you. This prevents the database from filling up with redundant information.

### Git Integration

ContextWolf can automatically track your commits via a post-commit hook. This is **not** set up automatically - you need to install the hook per repository:

```bash
cm git-init              # Install hook in current repo
cm git-init --global     # Install as git template (all future repos)
```

After installation, every `git commit` in that repo automatically saves the commit message, changed files, and branch info to ContextWolf. To update hooks across all your repos at once, use `python3 local/update_hooks.py` from the context-wolf directory.

---

## MCP Integration

After running `cm setup-mcp`, ContextWolf registers itself in `~/.claude.json` as an MCP server. Claude Code launches it automatically as a stdio subprocess.

### How it works

1. You start a new Claude Code session
2. Claude Code launches the ContextWolf MCP server in the background
3. Claude sees 31 tools (e.g., `context_save`, `context_search`, `todo_add`)
4. Claude uses these tools when relevant - saving decisions, searching for prior context, managing TODOs

### Available MCP Tools (overview)

| Category | Tools |
|---|---|
| Context | `context_save`, `context_search`, `context_show`, `context_move` |
| Notes | `note_save`, `note_search`, `note_show`, `note_edit`, `note_delete` |
| TODOs | `todo_add`, `todo_list`, `todo_start`, `todo_done`, `todo_show`, `todo_reopen`, `todo_cancel` |
| Infrastructure | `infra_list_hosts`, `infra_show_host`, `infra_list_services`, `infra_search`, `infra_add_host`, `infra_add_service` |
| Snippets | `snippet_search`, `snippet_show`, `snippet_add`, `snippet_list` |
| Meta | `session`, `stats`, `projects`, `ai_prompt`, `article_research` |

For full tool documentation with parameters, see [MCP_TOOLS.md](MCP_TOOLS.md).

### Prompting Claude to use ContextWolf

Claude can use these tools on its own, but does not always do so automatically. Helpful prompts:

- *"Use cm to search for our auth approach."*
- *"Save this decision in cm."*
- *"Check cm infra for the production server details."*
- *"Do we have open cm todos?"*

The shorthand `cm` works reliably because Claude maps it to the `context-manager` MCP tools.

> **Note on naming:** The project is called ContextWolf, but the MCP server key is `context-manager` (kept for backwards compatibility). In Claude Code sessions, referring to `cm` or `context-manager` is more reliable than saying "ContextWolf" since the tool definitions use the `context-manager` prefix.

Adding instructions to your project's `CLAUDE.md` (e.g., "Always use context_search before making architecture decisions") makes this more consistent.

---

## CLI vs MCP

| Use case | Recommended interface |
|---|---|
| Claude Code session (AI-driven) | MCP tools (automatic) |
| Quick manual lookup | CLI (`cm search "topic"`) |
| Batch operations | CLI (`cm-embed batch`) |
| System health check | CLI (`cm doctor`) |
| Setup and configuration | CLI (`cm init`, `cm setup-mcp`) |

The CLI offers 60+ commands - more than the 31 MCP tools. Some operations (like `cm doctor`, `cm init`, or `cm vacuum`) are CLI-only.

---

## Configuration

ContextWolf uses two files with identical database credentials:

- **`.env`** in the repo - used by Docker Compose
- **`~/.context/config.yaml`** - used by the CLI and MCP server

`cm init` reads `.env` and writes `config.yaml` so both stay in sync.

### config.yaml

```yaml
database:
  backend: postgres
  postgres:
    host: localhost
    port: 5432
    database: context_manager
    user: cm_user
    password: your_password_here
```

Environment variables (`POSTGRES_HOST`, `POSTGRES_PORT`, etc.) override YAML settings at runtime.

### .env

```bash
POSTGRES_USER=cm_user
POSTGRES_PASSWORD=your_password_here
POSTGRES_DB=context_manager
POSTGRES_PORT=5432
TZ=Europe/Berlin
```

Changed the password? Update both files, then `docker compose restart postgres`.

### Semantic Search (optional)

Semantic search uses a local ONNX embedding model (`all-MiniLM-L6-v2`, ~90 MB) to find conceptually similar entries. Search for "authentication" and find entries about "JWT", "login", or "OAuth".

```bash
# Process all unembedded entries
cm-embed batch

# Check embedding statistics
cm-embed stats
```

For automatic updates, set up a cron job using `embedding_worker/cron_embed.sh`.

---

## Entry Points

| Command | Description | Install extra |
|---|---|---|
| `cm` | CLI tool (33+ commands) | Core (no extra needed) |
| `cm-mcp` | MCP server for Claude Code | Core (no extra needed) |
| `cm-embed` | Embedding worker for semantic search | `uv sync --extra embeddings` |

---

## Development

If you modify ContextWolf source code, install it in editable mode so changes take effect immediately:

```bash
uv tool install -e .
```

Without `-e`, the `cm` command runs a frozen copy. Code changes won't be picked up until you reinstall. The `setup.sh` script installs without `-e` by design (stable for end users).

---

## Further Reading

- [MCP_TOOLS.md](MCP_TOOLS.md) - Full MCP tool reference with parameters
- [CLI_REFERENCE.md](CLI_REFERENCE.md) - Complete CLI command reference
- [CHANGELOG.md](../CHANGELOG.md) - Version history
