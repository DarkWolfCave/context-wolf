# ContextWolf

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB.svg)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-Server-8A2BE2.svg)](https://modelcontextprotocol.io)
[![pgvector](https://img.shields.io/badge/pgvector-Hybrid%20Search-336791.svg)](https://github.com/pgvector/pgvector)

A high-performance local knowledge system for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) via MCP integration.
Stores decisions, code snippets, infrastructure details, and TODOs - so your AI assistant never forgets what you've already decided.

![ContextWolf Demo](demo.gif)

## What it does

- **Cross-Project Search** - Full-text search + semantic vector search across all projects
- **MCP Integration** - 31 tools available directly in Claude Code sessions
- **Notes** - Long-form reference documents with tags and full-text search
- **Snippets** - Code snippet library with tags and type detection
- **Infrastructure Tracking** - Structured SSH host & service management
- **TODO Lifecycle** - Task tracking with priorities, categories, and status
- **Git Integration** - Post-commit hooks auto-track commits (opt-in per repo)
- **Duplicate Detection** - Warns at 85%+ similarity

## Why?

Claude Code is brilliant - but it has amnesia. Every time a session ends, all context is gone. Next session, it suggests Cassandra when you decided on PostgreSQL two weeks ago.

ContextWolf fixes this. It runs as a local MCP server alongside Claude Code, storing decisions, code patterns, and infrastructure details in your own PostgreSQL database. When Claude starts a new session, the knowledge is still there.

### How it works in practice

**Day 1** - You're debugging an auth issue with Claude:
```
You: "Claude, save this: we decided to use session cookies instead of JWTs for security."
Claude calls context_save → decision stored in ContextWolf.
```

**Day 14** - Fresh session, different feature:
```
You: "Claude, check what auth decisions we have before building the login route."
Claude calls context_search → finds your decision → implements session cookies, not JWTs.
```

No more repeating yourself. Your AI assistant finally has long-term memory.

> **How automatic is it?** Claude sees the ContextWolf tools via MCP and can use them anytime. But it won't reliably do so on its own - even with instructions in `CLAUDE.md`. In practice, you'll sometimes need to say "save this in ContextWolf" or "check ContextWolf first". Think of it as a tool Claude *can* use, not one it *always* uses. The more you use it, the more natural the workflow becomes.

### Why not just use Markdown files?

You could store context in `.md` files or `CLAUDE.md`. That works for small projects. But it doesn't scale:

- **Search** - Markdown files are loaded entirely into the context window. ContextWolf uses full-text search + vector similarity to return only relevant results.
- **Cross-project** - Markdown lives in one repo. ContextWolf searches across all your projects with one query.
- **Scale** - 7,000+ entries, search in ~1ms. A Markdown file with 1,000 lines costs tokens every time Claude reads it.
- **Semantic search** - Search for "authentication" and find entries about "JWT", "login", "OAuth". Markdown can't do that.
- **Structure** - Types, projects, tags, priorities, timestamps, duplicate detection. Not just free text.

## Prerequisites

- **Python 3.12+**
- **Docker** (recommended for PostgreSQL) or an existing PostgreSQL 13+ with [pgvector](https://github.com/pgvector/pgvector)

## Architecture

ContextWolf runs in two parts:

- **PostgreSQL + pgvector** (the storage) - one container, runs anywhere (local Docker, a Raspberry Pi, a NAS)
- **`cm-mcp`** (the MCP server) - always runs locally on your coding machine, launched by Claude Code via stdio

The optional GUI ([context-wolf-ui](https://github.com/DarkWolfCave/context-wolf-ui)) is a third component that reuses the same database - it never runs its own PostgreSQL instance.

## Quick Start

```bash
git clone https://github.com/DarkWolfCave/context-wolf.git
cd context-wolf
cp .env.example .env
# Edit .env and set POSTGRES_PASSWORD
bash setup.sh
```

That's it. The setup script will:
1. Install [uv](https://docs.astral.sh/uv/) (fast Python package manager) if needed
2. Install all dependencies
3. Start PostgreSQL via `docker compose up -d` (reads credentials from `.env`)
4. Write `~/.context/config.yaml` (CLI config, same credentials as `.env`)
5. Download the ONNX embedding model (~90 MB, for semantic search)
6. Configure Claude Code MCP integration
7. Run diagnostics to verify everything works

<details>
<summary>Manual setup (advanced)</summary>

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies (pick what you need)
uv sync                        # Core CLI + MCP server for Claude Code
uv sync --extra embeddings     # + Semantic search (ONNX, ~90 MB)
uv sync --extra all            # Everything

# Start PostgreSQL
cp .env.example .env
# edit .env, set POSTGRES_PASSWORD
docker compose up -d

# Configure CLI (reads .env for credentials)
cm init                        # Writes ~/.context/config.yaml

# Configure Claude Code
cm setup-mcp                   # Writes ~/.claude.json

# Check everything
cm doctor
```

</details>

### Configuration files

Two files with identical credentials:

- **`.env`** - used by Docker Compose when starting PostgreSQL
- **`~/.context/config.yaml`** - used by the CLI and MCP server to connect

`cm init` reads `.env` and writes `config.yaml` so both stay in sync. Change the password? Edit both files, restart the container, and run `cm init` again.

### Data location

By default, PostgreSQL data is stored in `./data/postgres/` next to `docker-compose.yml` (the directory is gitignored). This makes the data easy to find, back up, or delete.

To store data elsewhere (e.g., in your home directory or on a separate SSD), edit the `volumes:` line in `docker-compose.yml`. Examples are in the comments at the top of that file.

## Setup Script Options

```bash
bash setup.sh                  # Full interactive setup
bash setup.sh --install-only   # Only install dependencies
bash setup.sh --doctor         # Run diagnostics
bash setup.sh --init           # Configure database
bash setup.sh --setup-mcp      # Configure Claude Code MCP
```

### Database on a separate server

If you want PostgreSQL on a different machine (e.g., a Raspberry Pi or NAS) and the MCP server on your local machine:

```bash
# 1. On the server: clone the repo, configure .env, start PostgreSQL
ssh user@your-server
git clone https://github.com/DarkWolfCave/context-wolf.git
cd context-wolf
cp .env.example .env
# Edit .env, set POSTGRES_PASSWORD
docker compose up -d

# 2. On your local machine: install CLI, choose "External server"
git clone https://github.com/DarkWolfCave/context-wolf.git
cd context-wolf
bash setup.sh --install-only
cm init
# → Option [2], enter the server's IP, port 5432, matching user/password
cm setup-mcp
```

> **Security note:** The compose file exposes PostgreSQL on port 5432 on all network interfaces of the server. For untrusted networks, restrict access with a firewall, bind to a specific IP (edit the `ports:` line: `"192.168.1.37:5432:5432"`), or tunnel through Tailscale/WireGuard. PostgreSQL is password-protected but raw port exposure is still a surface area.

## Usage

### CLI

```bash
# Save context
cm save "Implemented JWT auth with refresh tokens"

# Search
cm search "authentication"           # Current project
cm search "auth" --all               # All projects
cm smart-search "XSS prevention"     # Universal search (instructions + snippets + actions)

# Session & stats
cm session                           # Today's activity
cm stats                             # Database statistics
cm doctor                            # System health check

# TODOs
cm todo add "Fix auth bug" --priority high
cm todo start 123
cm todo done 123

# AI Instructions
cm ai-instruction "Always use snake_case" --category style --priority should

# Infrastructure
cm infra add-host "web01" --ip 10.0.0.1 --user deploy --location extern
cm infra list-hosts
```

### MCP Server (Claude Code)

Automatically configured by `bash setup.sh` or `cm setup-mcp`. Exposes 31 tools: `context_save`, `context_search`, `todo_add`, `infra_list_hosts`, `infra_add_host`, `note_save`, and more.

See [docs/MCP_TOOLS.md](docs/MCP_TOOLS.md) for the full list.

<details>
<summary>Manual MCP configuration</summary>

Add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "context-manager": {
      "command": "uv",
      "args": ["--directory", "/path/to/context-wolf", "run", "cm-mcp"]
    }
  }
}
```

</details>

### Embedding Worker (Semantic Search)

```bash
cm-embed batch              # Process all unembedded entries
cm-embed stats              # Show embedding statistics
```

For automatic updates, set up a cron job or launchd timer (see `embedding_worker/cron_embed.sh`).

## Privacy & Token Economy

**Your data stays yours.** ContextWolf runs entirely on your infrastructure:

- **Local database** - PostgreSQL on your machine, NAS, or Raspberry Pi. Your stored data stays on your infrastructure. (Note: Your conversation with Claude itself goes through Anthropic's API as usual - ContextWolf doesn't change that.)
- **Local embeddings** - Semantic search uses a lightweight ONNX model (all-MiniLM-L6-v2, ~90 MB) running on your CPU. Zero API calls for vector generation.
- **On-demand retrieval** - ContextWolf does NOT inject your entire database into Claude's context. MCP tools return only the relevant results for the current query (ranked by full-text search + vector similarity).

**Token overhead:** The 31 MCP tool definitions are deferred by default - only tool names are loaded at session start (~356 tokens). Full schemas are fetched on-demand when Claude actually uses a tool. The actual data is only retrieved when a tool is called.

## Architecture

```
src/
├── core/        # Database, config, backends (PostgreSQL)
├── domain/      # Business logic (actions, search, sessions)
├── features/    # Modules (snippets, TODOs, notes, infra, AI instructions)
└── cli/         # Argument parser + command handlers + setup wizard

mcp_server/      # MCP integration (stdio, 31 tools)
embedding_worker/ # ONNX-based vector embeddings (all-MiniLM-L6-v2)
```

Clean Architecture with 4 layers: CLI → Features → Domain → Core.
Dependencies flow inward only.

## Entry Points

| Command | Description | Requires |
|---------|-------------|----------|
| `cm` | CLI tool | Core |
| `cm-mcp` | MCP server (stdio) | Core |
| `cm-embed` | Embedding worker | `[embeddings]` extra |

## Documentation

- [docs/USER_GUIDE.md](docs/USER_GUIDE.md) - Getting started guide
- [docs/MCP_TOOLS.md](docs/MCP_TOOLS.md) - MCP tools reference (31 tools)
- [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md) - Complete CLI command reference
- [CHANGELOG.md](CHANGELOG.md) - Version history

## Background

ContextWolf started as a simple CLI tool to help me keep context across Claude Code sessions. No MCP, no vector search - just saving and retrieving decisions so I wouldn't repeat myself.

It grew from there, one feature at a time, based on whatever I needed next: notes, TODOs, infrastructure tracking, code snippets, semantic search. I used earlier versions in production for quite a while before several people suggested I should make it publicly available. That led to V5 - a cleanup and restructure for open source release.

That said, this is a personal project that grew organically over multiple versions. There may still be rough edges or leftover code from earlier iterations. If you find something broken or improvable, please [open an issue](https://github.com/DarkWolfCave/context-wolf/issues) or submit a PR. Contributions are welcome.

## License

MIT - see [LICENSE](LICENSE) for details.
