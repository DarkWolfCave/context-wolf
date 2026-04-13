# ContextWolf

A high-performance local knowledge system for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) via MCP integration.
Stores decisions, code snippets, infrastructure details, and TODOs - so your AI assistant never forgets what you've already decided.

## What it does

- **Cross-Project Search** - Full-text search + semantic vector search across all projects
- **MCP Integration** - 31 tools available directly in Claude Code sessions
- **Infrastructure Tracking** - Structured SSH host & service management
- **TODO Lifecycle** - Task tracking with priorities, categories, and status
- **Git Integration** - Auto-tracks commits via post-commit hooks
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

## Quick Start

```bash
git clone https://github.com/DarkWolfCave/context-wolf.git
cd context-wolf
bash setup.sh
```

That's it. The setup script will:
1. Install [uv](https://docs.astral.sh/uv/) (fast Python package manager) if needed
2. Install all dependencies
3. Walk you through database configuration (Docker or external PostgreSQL)
4. Configure Claude Code MCP integration
5. Run diagnostics to verify everything works

<details>
<summary>Manual setup (advanced)</summary>

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies (pick what you need)
uv sync                        # Core CLI only
uv sync --extra mcp            # + MCP server for Claude Code
uv sync --extra embeddings     # + Semantic search (ONNX, ~200MB)
uv sync --extra all            # Everything

# Configure database
cm init                        # Interactive wizard

# Configure Claude Code
cm setup-mcp                   # Writes ~/.claude.json

# Check everything
cm doctor
```

</details>

## Setup Script Options

```bash
bash setup.sh                  # Full interactive setup
bash setup.sh --install-only   # Only install dependencies
bash setup.sh --doctor         # Run diagnostics
bash setup.sh --init           # Configure database
bash setup.sh --setup-mcp      # Configure Claude Code MCP
```

### Database on a separate server

If you want PostgreSQL on a different machine (e.g., a Raspberry Pi or NAS):

```bash
# 1. Copy docker-compose.yml to the server
scp docker-compose.yml user@your-server:~/context-wolf/

# 2. IMPORTANT: The default config binds to localhost only (127.0.0.1).
#    For remote access, edit docker-compose.yml on the server and change:
#      "127.0.0.1:5432:5432"  →  "5432:5432"
#    This allows connections from your local machine over the network.

# 3. Start PostgreSQL there
ssh user@your-server "cd ~/context-wolf && docker compose up -d"

# 4. On your local machine, choose "External server" during setup
cm init
# → Option [2], then enter the server's IP, port 5432, user cm_user, password
```

> **Security note:** `127.0.0.1:5432:5432` (default) means only processes on the same machine can connect - ideal when DB and app run on the same host. Changing to `5432:5432` exposes the port on all network interfaces. If your server is accessible from untrusted networks, use a firewall or bind to a specific IP (e.g., `192.168.1.37:5432:5432`).

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
cm infra add-host "web01" --ip 10.0.0.1 --user deploy --location dc-1
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
- **Local embeddings** - Semantic search uses a lightweight ONNX model (all-MiniLM-L6-v2, 86MB) running on your CPU. Zero API calls for vector generation.
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
| `cm-mcp` | MCP server (stdio) | `[mcp]` extra |
| `cm-embed` | Embedding worker | `[embeddings]` extra |

## Documentation

- [docs/USER_GUIDE.md](docs/USER_GUIDE.md) - Getting started guide
- [docs/MCP_TOOLS.md](docs/MCP_TOOLS.md) - MCP tools reference (31 tools)
- [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md) - Complete CLI command reference
- [CHANGELOG.md](CHANGELOG.md) - Version history

## License

MIT - see [LICENSE](LICENSE) for details.
