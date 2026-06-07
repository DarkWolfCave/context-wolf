# ContextWolf CLI Reference (V5.1.0)

Complete reference for the `cm` command-line interface.

> **Installation:** Run `./setup.sh` to install ContextWolf. This registers the `cm`, `cm-mcp`, and `cm-embed` entry points.

---

## Entry Points

| Command | Purpose |
|---------|---------|
| `cm` | Main CLI - all commands below |
| `cm-mcp` | Start the MCP server (used by Claude Code) |
| `cm-embed` | Embedding worker for semantic search |

## Global Flags

| Flag | Description |
|------|-------------|
| `--version`, `-V` | Show version |

---

## Core Commands

### save

Save an action, decision, or code context.

```
cm save <content> [options]
```

| Option | Description |
|--------|-------------|
| `--type`, `-t` | Type: `code`, `decision`, `fix`, `command` |
| `--project`, `-p` | Project name |
| `--metadata`, `-m` | JSON metadata string |

### search

Full-text search across saved entries.

```
cm search <query> [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--type`, `-t` | - | Filter by type |
| `--limit`, `-l` | 20 | Max results |
| `--days`, `-d` | - | Last N days |
| `--date-from` | - | Start date (YYYY-MM-DD) |
| `--date-to` | - | End date (YYYY-MM-DD) |
| `--date` | - | Single date (YYYY-MM-DD) |
| `--project`, `-p` | - | Specific project |
| `--all`, `-a` | - | Search ALL projects |

### smart-search

Universal search across all content types (actions, instructions, snippets).

```
cm smart-search <query> [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--limit`, `-l` | 20 | Max total results |
| `--per-type` | 5 | Max results per type |
| `--types` | - | Filter: `instructions`, `snippets`, `actions` |

### show / delete / related

```
cm show <entry_id>
cm delete <id> [--force, -f]
cm related <id> [--limit, -l <n>]       # default: 10
```

### projects

```
cm projects
cm project-delete <name> [--force, -f]
```

### session / stats

```
cm session [--id <session_id>] [--verbose, -v]
cm stats
```

### vacuum

Optimize the database (reclaim space, rebuild indexes).

```
cm vacuum
```

### index

Index Markdown files into ContextWolf.

```
cm index [directory]       # default: current directory
```

### tool-stats

Show MCP tool usage statistics.

```
cm tool-stats [--days, -d <n>] [--export, -e json|csv]    # default: 30 days
```

### cleanup

Cleanup entries and sessions.

```
cm cleanup [options]
```

| Option | Description |
|--------|-------------|
| `--orphaned` | Remove entries for deleted files |
| `--legacy` | List entries without file tracking |
| `--stats` | File tracking statistics |
| `--force` | Skip confirmation |
| `--sessions` | Cross-project sessions |
| `--normalize-sessions` | Normalize session IDs |

**Examples - Core Commands:**

```bash
cm save "Switched from JWT to session cookies" -t decision -p myapp
cm search "authentication" --days 30
cm smart-search "deployment workflow" --types instructions
cm search "database migration" --date-from 2025-01-01 --date-to 2025-06-30
cm related 42 --limit 5
cm cleanup --orphaned --force
```

---

## Snippet Commands

Manage reusable code snippets.

### snippet-add

```
cm snippet-add <file_path> [options]
```

| Option | Description |
|--------|-------------|
| `--name`, `-n` | Snippet name |
| `--desc`, `-d` | Description |
| `--tags`, `-t` | Tags (can be repeated) |
| `--store`, `-s` | Store full file content |

### snippet-search

```
cm snippet-search [query] [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--type`, `-t` | - | Filter by file type |
| `--tags` | - | Filter by tags |
| `--limit`, `-l` | 20 | Max results |

### snippet-show / snippet-list / snippet-delete

```
cm snippet-show <name> [--cat, -c]       # -c shows full content
cm snippet-list
cm snippet-delete <name> [--force, -f]
```

**Examples - Snippets:**

```bash
cm snippet-add ./src/auth/middleware.py -n "auth-middleware" -d "JWT validation" -t python -t auth --store
cm snippet-search "middleware" --type py --limit 10
cm snippet-show auth-middleware --cat
```

---

## Git Commands

Track commits and install git hooks.

```
cm git-init [--force] [--global]         # Install git hook
cm git-info                              # Show git repository info
cm commit-info [id] [--hash <sha>] [--last, -l]   # Show commit details
```

**Examples - Git:**

```bash
cm git-init --force
cm commit-info --last
cm commit-info --hash abc1234
```

---

## AI Commands

### ai-prompt

Generate a context-aware prompt for a new AI session.

```
cm ai-prompt [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--quick`, `-q` | - | Quick mode |
| `--verbose`, `-v` | - | Verbose mode |
| `--smart` | - | Session-aware filtering |
| `--hours` | 24 | Time window for smart mode |
| `--project`, `-p` | - | Project name |

### ai-instruction

Manage persistent AI instructions (coding standards, rules, preferences).

```
cm ai-instruction [instruction] [options]
```

**Create / Update:**

| Option | Description |
|--------|-------------|
| `--scope`, `-s` | `global`, `project`, `session` (default: project) |
| `--priority`, `-pr` | `must`, `should`, `nice` (default: should) |
| `--category`, `-c` | `security`, `style`, `performance`, `architecture`, `testing`, `general` |
| `--rationale`, `-r` | Reasoning behind the instruction |

**Query:**

| Option | Description |
|--------|-------------|
| `--list`, `-l` | List all instructions |
| `--show <id>` | Show specific instruction |
| `--search <term>` | Search instructions |
| `--search-category` | Filter by category |
| `--search-priority` | Filter by priority |
| `--search-scope` | Filter by scope |

**Manage:**

| Option | Description |
|--------|-------------|
| `--toggle <id>` | Toggle active/inactive |
| `--delete <id>` | Delete instruction |
| `--template`, `-t` | Load instruction from template |
| `--project`, `-p` | Project name |

### ai-instruction-update

Update an existing AI instruction.

```
cm ai-instruction-update <id> [options]
```

| Option | Description |
|--------|-------------|
| `--scope`, `-s` | Change scope |
| `--priority`, `-pr` | Change priority |
| `--category`, `-c` | Change category |
| `--toggle`, `-t` | Toggle active state |
| `--instruction` | New instruction text |
| `--rationale`, `-r` | New rationale |
| `--clear-rationale` | Remove rationale |
| `--example-good` | Add positive example |
| `--example-bad` | Add negative example |
| `--clear-examples` | Remove all examples |

**Examples - AI:**

```bash
cm ai-prompt --smart --hours 48
cm ai-instruction "Always use type hints in Python" -s global -pr must -c style
cm ai-instruction --list --search-category security
cm ai-instruction-update 5 --priority must --example-good "def greet(name: str) -> str:"
```

---

## TODO Commands

Task management with priorities, dependencies, and assignments.

All TODO commands use the `todo` subcommand prefix.

### todo add

```
cm todo add <summary> [options]
```

| Option | Description |
|--------|-------------|
| `--content`, `-c` | Detailed description |
| `--priority`, `-p` | `high`, `normal`, `low` |
| `--category`, `-cat` | Category name |
| `--due`, `-d` | Due date (YYYY-MM-DD) |
| `--tags`, `-t` | Tags (can be repeated) |
| `--depends` | Dependent TODO IDs |
| `--assign`, `-a` | Assignee |
| `--project` | Project name |

### todo list

```
cm todo list [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--status`, `-s` | - | Filter by status |
| `--priority`, `-p` | - | Filter by priority |
| `--category`, `-cat` | - | Filter by category |
| `--assigned`, `-a` | - | Filter by assignee |
| `--all` | - | Include done items |
| `--all-projects` | - | Show all projects |
| `--project` | - | Specific project |
| `--limit`, `-l` | 50 | Max results |

### todo lifecycle

```
cm todo start <id>
cm todo done <ids...> [--force, -f]
cm todo reopen <ids...>
cm todo cancel <ids...>
cm todo delete <ids...> [--force, -f]
```

### todo show / stats / stale / suggest

```
cm todo show <id>
cm todo stats [--project <name>]
cm todo stale [--days, -d <n>]           # default: 7
cm todo suggest [--project <name>] [--limit, -l <n>]   # default: 5
```

**Examples - TODO:**

```bash
cm todo add "Implement rate limiting" -p high -cat security --due 2025-04-15 -t backend
cm todo list -s open -p high
cm todo start 42
cm todo done 42 43 44
cm todo stale --days 14
```

---

## Test Commands

Test suite management and execution tracking.

All test commands use the `test` subcommand prefix.

### test suite-add / suite-list / suite-update

```
cm test suite-add <name> [--desc <text>] [--project, -p <name>] [--tags <tags>]
cm test suite-list [--project, -p <name>] [--all]
cm test suite-update <suite_id> [--name <n>] [--desc <d>] [--tags <t>]
```

### test case-add

```
cm test case-add <suite_id> <name> <command> [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--desc` | - | Description |
| `--cwd` | - | Working directory |
| `--timeout` | 300 | Timeout in seconds |
| `--exit-code` | 0 | Expected exit code |
| `--priority` | - | Priority level |
| `--tags` | - | Tags |

### test case-list / case-update

```
cm test case-list [--suite <id>] [--priority <p>] [--all]
cm test case-update <test_case_id> [--name] [--desc] [--command] [--cwd] [--timeout] [--exit-code] [--priority] [--tags]
```

### test exec / run-suite

```
cm test exec <test_case_id> [--save-output] [--env KEY=VALUE]
cm test run-suite <suite_id> [--priority <p>] [--stop-on-fail]
```

### test history / stats / failures / flaky / coverage

```
cm test history <test_case_id> [--limit, -l <n>]    # default: 10
cm test stats [--suite <id>] [--case <id>] [--project, -p <name>] [--days <n>]   # default: 30
cm test failures [--project, -p <name>] [--limit, -l <n>]   # default: 10
cm test flaky [--project, -p <name>] [--min-runs <n>]       # default: 5
cm test coverage <project>
```

**Examples - Test:**

```bash
cm test suite-add "API Tests" --desc "REST endpoint tests" -p myapp
cm test case-add 1 "health-check" "curl -sf http://localhost:8000/health" --timeout 10
cm test run-suite 1 --stop-on-fail
cm test failures --limit 5
cm test flaky --min-runs 10
```

---

## Infrastructure Commands

Track SSH hosts and deployed services.

All infrastructure commands use the `infra` subcommand prefix.

### infra add-host

```
cm infra add-host <hostname> [options]
```

| Option | Description |
|--------|-------------|
| `--ip` | IP address |
| `--port` | SSH port (default: 22) |
| `--user`, `-u` | SSH user |
| `--identity-file`, `-i` | SSH key path |
| `--location`, `-l` | `local` or `extern` |
| `--provider` | Hosting provider |
| `--server-type` | Server type |
| `--scope` | `global` or `project` |
| `--project`, `-p` | Project name |
| `--tags`, `-t` | Tags (can be repeated) |
| `--comment`, `-c` | Comment |

### infra list-hosts / show-host / edit-host / delete-host

```
cm infra list-hosts [--scope <s>] [--location, -l <loc>] [--project, -p <name>] [--tags, -t <tags>] [--minimal, -m]
cm infra show-host <hostname>
cm infra edit-host <hostname> [--ip] [--port] [--user] [--identity-file] [--location] [--provider] [--server-type] [--scope] [--project] [--tags] [--comment]
cm infra delete-host <hostname> [--force, -f]
```

### infra add-service

```
cm infra add-service <hostname> <service_name> [options]
```

| Option | Description |
|--------|-------------|
| `--env`, `-e` | `prod`, `staging`, `dev`, `test` |
| `--path` | Deployment path |
| `--type` | Service type |
| `--deploy-method` | Deployment method |
| `--health-url` | Health check URL |
| `--scope` | `global` or `project` |
| `--project`, `-p` | Project name |
| `--tags`, `-t` | Tags |
| `--comment`, `-c` | Comment |

### infra list-services / edit-service / delete-service

```
cm infra list-services [--host <name>] [--env, -e <env>] [--scope <s>] [--project, -p <name>]
cm infra edit-service <hostname> <service_name> [--env] [--path] [--type] [--deploy-method] [--health-url] [--scope] [--project] [--tags] [--comment]
cm infra delete-service <hostname> <service_name>
```

**Examples - Infrastructure:**

```bash
cm infra add-host prod-server-01 --ip 10.0.1.5 -u deploy -l local --tags production --tags docker
cm infra add-service prod-server-01 "web-api" -e prod --health-url http://10.0.1.5:8000/health --deploy-method docker
cm infra list-hosts --location local --minimal
cm infra list-services --env prod
```

---

## Now Commands

Cross-project sprint backlog with WIP limits. Three active buckets
(`today` / `week` / `later`) plus a 24h `done` holding bucket. Items
can either stand alone or reference an existing CM entity (TODO, note,
snippet, action, AI instruction, host, service); `now list` shows the
linked entity's live status.

All Now commands use the `now` subcommand prefix.

### now add

Add an item to the Now list. Refuses to add when the bucket's WIP
limit is reached - move or remove an existing item first.

```
cm now add <title> [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--bucket`, `-b` | `today` | Target bucket: `today`, `week`, `later` |
| `--project`, `-p` | - | Project name (cross-project is fine) |
| `--link-type` | - | Reference an existing CM entity: `todo`, `action`, `note`, `snippet`, `ai_instruction`, `host`, `service` |
| `--link-id` | - | ID of the linked entity (required with `--link-type`) |

### now list

List Now items, grouped by bucket with capacity indicators.

```
cm now list [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--bucket`, `-b` | - | Filter: `today`, `week`, `later`, `done` |
| `--project`, `-p` | - | Filter by project |
| `--all` | - | Include the `done` bucket |
| `--json` | - | Emit the raw JSON response (the UI contract) |

### now lifecycle

```
cm now show <id>                       # show one item with link payload
cm now move <id> <bucket>              # bucket: today | week | later
cm now done <id>                       # mark as done (24h holding)
cm now remove <id>                     # hard-delete (drop, not finish)
```

### now reorder

Rewrite the order of items in a bucket (drag-and-drop result). `ids`
must list every item currently in the bucket exactly once.

```
cm now reorder <bucket> <ids...>
```

### now settings

Show current WIP limits, or update one or more (range 1-100).

```
cm now settings                        # show current limits
cm now settings --today 5              # change one limit
cm now settings --today 5 --week 15    # change multiple
```

| Option | Description |
|--------|-------------|
| `--today` | New limit for `today` |
| `--week` | New limit for `week` |
| `--later` | New limit for `later` |

**Examples - Now:**

```bash
cm now add "Fix DSGVO footer link" -b today -p myapp
cm now add "Polish settings dialog" --link-type todo --link-id 42
cm now list
cm now move 5 week
cm now done 5
cm now reorder today 7 5 3 2 1
cm now settings --today 5
```

---

## Pinned Commands

**Read-only from the CLI.** Pinning items is a feature of the optional
[context-wolf-ui](https://github.com/DarkWolfCave/context-wolf-ui) GUI -
the CLI can only list what you've pinned there. Without the GUI, the
pinned_items table doesn't exist and `cm pinned` returns empty (no error).

### pinned

```
cm pinned [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--project`, `-p` | - | Filter by project (returns global items + items scoped to this project) |
| `--json` | Markdown | Output as JSON instead of the default grouped Markdown |

**Behavior:**

- Without GUI / missing tables: returns an empty list or a friendly placeholder message - never errors.
- Without `--project`: all pinned items across all scopes, globals first.
- With `--project X`: global items plus items explicitly scoped to project `X`.

**Examples:**

```bash
cm pinned
cm pinned --project myapp
cm pinned --json > /tmp/pinned.json
```

**Not exposed via MCP:** `pinned` is a user-triggered helper (you decide when to paste it into a prompt), so it is intentionally not registered as an MCP tool. This keeps the MCP tool schema lean.

---

## Setup Commands

Initial setup and diagnostics.

```
cm init                  # Interactive setup wizard (DB config, Docker start)
cm doctor                # Check prerequisites and system health
cm setup-mcp             # Configure MCP server in Claude Code
```

---

## Quick Reference

| Command | Purpose |
|---------|---------|
| `cm save` | Save context entry |
| `cm search` | Full-text search |
| `cm smart-search` | Cross-type search |
| `cm show` / `cm delete` | View / remove entry |
| `cm related` | Find related entries |
| `cm projects` | List projects |
| `cm session` | Current session info |
| `cm stats` | Usage statistics |
| `cm vacuum` | Optimize database |
| `cm index` | Index Markdown files |
| `cm tool-stats` | MCP tool usage |
| `cm cleanup` | Cleanup entries |
| `cm snippet-*` | Code snippet management |
| `cm git-init` / `cm git-info` | Git integration |
| `cm commit-info` | Commit details |
| `cm ai-prompt` | Generate AI prompt |
| `cm ai-instruction` | Manage AI rules |
| `cm todo *` | Task management |
| `cm test *` | Test suite management |
| `cm infra *` | Infrastructure tracking |
| `cm now *` | Sprint backlog (today / week / later) |
| `cm pinned` | List GUI-curated pinned items (read-only) |
| `cm init` / `cm doctor` | Setup and diagnostics |
| `cm setup-mcp` | MCP configuration |
