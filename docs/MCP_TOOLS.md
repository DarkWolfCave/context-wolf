# ContextWolf V5.0.0 - MCP Tools Reference

Complete reference for all 31 MCP tools exposed by ContextWolf. Intended for developers using these tools via Claude Code.

---

## Context Management

### `context_save`

Save an action or decision to context manager. If no project specified, saves to 'global'.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `content` | string | Yes | What was done or decided |
| `type` | string | No | Type of action. Enum: `code`, `fix`, `feature`, `decision`, `refactor`, `test`, `doc`, `command` |
| `project` | string | No | Project name (defaults to `global`) |

### `context_move`

Move a context entry to a different project.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `entry_id` | integer\|string | Yes | The entry ID to move |
| `project` | string | Yes | Target project name |

### `context_search`

Search the context database.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | Yes | - | Search term |
| `type` | string | No | - | Filter by type |
| `project` | string | No | - | Project name, `current`, or `all` |
| `limit` | integer | No | 20 | Max results |

### `context_show`

Show full content of a specific context entry by ID. Use after `context_search` to see complete details.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `entry_id` | integer\|string | Yes | The context entry ID to show |

**Example:**

```
context_search(query="docker config", project="current")
# → entry #42 looks relevant
context_show(entry_id=42)
```

---

## Snippet Management

### `snippet_search`

Search for code snippets.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | No | Search term |
| `file_type` | string | No | Filter by file type |
| `tags` | array[string] | No | Filter by tags |

### `snippet_show`

Show full content of a specific snippet.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `snippet_id` | integer\|string | No | Snippet ID |
| `name` | string | No | Snippet name (alternative to ID) |

### `snippet_add`

Add a code snippet or template to the database.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | Yes | Path to the file to add |
| `name` | string | No | Name for the snippet (default: filename) |
| `description` | string | No | Description |
| `tags` | array[string] | No | Tags for categorization |
| `store_content` | boolean | No | Store full file content in DB (default: false) |

### `snippet_list`

List all code snippets in the database.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 100 | Max results |

**Example:**

```
snippet_add(file_path="src/utils/sanitizer.py", name="security-sanitizer", tags=["python", "security"])
snippet_list()
snippet_search(tags=["python", "security"])
snippet_show(snippet_id=7)
```

---

## TODO Management

### `todo_add`

Add a TODO task to track work. By default scoped to current project.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `content` | string | Yes | TODO content |
| `priority` | string | No | Enum: `high`, `normal`, `low` |
| `category` | string | No | Category |
| `project` | string | No | Project name (defaults to `default`) |

### `todo_list`

List TODO tasks. Default scope is `project`.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `status` | string | No | - | Enum: `open`, `in_progress`, `done`, `cancelled` |
| `priority` | string | No | - | Enum: `high`, `normal`, `low` |
| `scope` | string | No | - | Enum: `project`, `all` |
| `project` | string | No | - | Project name (required when scope=`project`) |

### `todo_start`

Start working on a TODO task.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `todo_id` | integer\|string | Yes | TODO ID to start |

### `todo_done`

Mark a TODO task as done.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `todo_id` | integer\|string | Yes | TODO ID to complete |

### `todo_show`

Show details of a specific TODO by ID.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `todo_id` | integer\|string | Yes | TODO ID to show |

### `todo_reopen`

Reopen a completed or cancelled TODO task.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `todo_id` | integer\|string | Yes | TODO ID to reopen |

### `todo_cancel`

Cancel a TODO task.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `todo_id` | integer\|string | Yes | TODO ID to cancel |

**Example:**

```
todo_add(content="Implement rate limiting", priority="high")
# → TODO #15 created
todo_start(todo_id=15)
todo_show(todo_id=15)
# ... decide to defer ...
todo_cancel(todo_id=15)
# ... later ...
todo_reopen(todo_id=15)
todo_done(todo_id=15)
```

---

## Core Utilities

### `session`

Show current session or a specific session.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | No | Session ID (default: current) |
| `verbose` | boolean | No | Show detailed output |

### `stats`

Show project statistics.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project` | string | No | Project name |

### `projects`

List all projects with statistics.

*No parameters.*

### `ai_prompt`

Generate AI session prompt with current context. Smart mode uses session-aware filtering.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `quick` | boolean | No | - | Quick mode (less verbose) |
| `verbose` | boolean | No | - | Verbose mode (more details) |
| `smart` | boolean | No | - | Smart mode: session-aware context filtering |
| `hours` | integer | No | 24 | Hours to look back for smart mode |

**Example:**

```
session()
stats(project="context-wolf")
ai_prompt(smart=true, hours=48)
```

---

## Infrastructure Management

### `infra_list_hosts`

List infrastructure SSH hosts. Minimal output by default for token efficiency.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `scope` | string | No | - | Enum: `global`, `project` |
| `location` | string | No | - | Enum: `local`, `extern` |
| `project_name` | string | No | - | Filter by project |
| `minimal` | boolean | No | true | Minimal output for token efficiency |

### `infra_show_host`

Show detailed info about a specific SSH host including services.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `hostname` | string | Yes | The hostname (e.g., `prod-server-01`) |

### `infra_list_services`

List services on infrastructure hosts.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `hostname` | string | No | Filter by hostname |
| `env` | string | No | Enum: `prod`, `staging`, `dev`, `test` |
| `scope` | string | No | Enum: `global`, `project` |
| `project_name` | string | No | Filter by project |

### `infra_search`

Search infrastructure hosts and services.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | Yes | - | Search term |
| `limit` | integer | No | 5 | Max results per category |

### `infra_add_host`

Add a new SSH host to infrastructure management.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `hostname` | string | Yes | - | SSH hostname (e.g., `prod-server-01`) |
| `ip` | string | No | - | IP address |
| `port` | integer | No | 22 | SSH port |
| `user` | string | No | - | SSH user |
| `identity_file` | string | No | - | Path to SSH key |
| `location` | string | No | - | Enum: `local`, `extern` |
| `provider` | string | No | - | Provider (e.g., `Netcup`, `Hetzner`) |
| `server_type` | string | No | - | Type (e.g., `VPS`, `Raspberry Pi`) |
| `scope` | string | No | - | Enum: `global`, `project` |
| `project_name` | string | No | - | Project (only when scope=`project`) |
| `tags` | array[string] | No | - | Tags |
| `comment` | string | No | - | Comment |

### `infra_add_service`

Add a service to an existing infrastructure host.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `hostname` | string | Yes | Host where the service runs (must exist) |
| `service_name` | string | Yes | Service name (e.g., `my-webapp`) |
| `env` | string | No | Enum: `prod`, `staging`, `dev`, `test` |
| `app_path` | string | No | Application path on host |
| `service_type` | string | No | Type (e.g., `docker`, `systemd`) |
| `deploy_method` | string | No | Deploy method (e.g., `ssh`, `local`) |
| `project_name` | string | No | Project to associate with |
| `tags` | array[string] | No | Tags |
| `comment` | string | No | Comment |

**Example:**

```
infra_add_host(hostname="web-prod", ip="10.0.0.5", user="deploy", location="extern", provider="Hetzner")
infra_add_service(hostname="web-prod", service_name="myapp", env="prod", service_type="docker")
infra_list_hosts(location="extern")
infra_show_host(hostname="web-prod")
```

---

## Notes Management

### `note_save`

Save a project note (Markdown). For long-lived documents, NOT session documentation.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `title` | string | Yes | Note title (max 200 chars) |
| `content` | string | Yes | Markdown content |
| `project` | string | No | Project name |
| `tags` | string | No | Comma-separated tags |

### `note_search`

Search project notes by keyword, project, or tags.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | No | - | Search term |
| `project` | string | No | - | Filter by project |
| `tags` | string | No | - | Filter by tag |
| `limit` | integer | No | 20 | Max results |

### `note_show`

Show full content of a specific note by ID.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `note_id` | integer\|string | Yes | Note ID to show |

### `note_edit`

Edit an existing note. Only provided fields are updated.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `note_id` | integer\|string | Yes | Note ID to edit |
| `title` | string | No | New title (max 200 chars) |
| `content` | string | No | New content (replaces existing) |
| `append` | string | No | Text to append to existing content |
| `tags` | string | No | New tags |

### `note_delete`

Delete a note by ID.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `note_id` | integer\|string | Yes | Note ID to delete |

**Example:**

```
note_save(title="Deploy Checklist", content="## Steps\n- Build\n- Test\n- Push", tags="ops,deploy")
note_search(tags="deploy")
note_edit(note_id=5, append="\n- Verify health endpoint")
```

---

## Article Research

### `article_research`

Research a topic across all CM entries. Creates a structured dossier with clusters and pattern detection.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `topic` | string | Yes | - | Research topic |
| `queries` | array[string] | No | - | Explicit search queries |
| `project` | string | No | - | Filter by project |
| `days_back` | integer | No | - | Limit to last N days |
| `save_as_note` | boolean | No | false | Save dossier as CM note |
| `note_project` | string | No | - | Project for saved note |

**Token warning:** This tool can return large responses (up to 100KB). It searches up to 60 FTS + 20 vector results, renders clusters, type groups, patterns, and all entry IDs. Use `project` and `days_back` filters to limit scope. For broad topics, expect 5,000-15,000+ tokens in the response.

**Example:**

```
# Scoped research (recommended - limits token usage)
article_research(topic="authentication", project="cronwolf", days_back=30)

# Broad research (can be very large!)
article_research(topic="PostgreSQL", save_as_note=true)
```

---

## Summary

| # | Tool | Category | Description |
|---|------|----------|-------------|
| 1 | `context_save` | Context | Save action or decision |
| 2 | `context_move` | Context | Move entry to another project |
| 3 | `context_search` | Context | Search context database |
| 4 | `context_show` | Context | Show full context entry |
| 5 | `snippet_search` | Snippets | Search code snippets |
| 6 | `snippet_show` | Snippets | Show full snippet |
| 7 | `snippet_add` | Snippets | Add a code snippet |
| 8 | `snippet_list` | Snippets | List all snippets |
| 9 | `todo_add` | TODO | Add a task |
| 10 | `todo_list` | TODO | List tasks |
| 11 | `todo_start` | TODO | Start a task |
| 12 | `todo_done` | TODO | Complete a task |
| 13 | `todo_show` | TODO | Show task details |
| 14 | `todo_reopen` | TODO | Reopen a task |
| 15 | `todo_cancel` | TODO | Cancel a task |
| 16 | `session` | Core | Show session info |
| 17 | `stats` | Core | Show project statistics |
| 18 | `projects` | Core | List all projects |
| 19 | `ai_prompt` | Core | Generate AI session prompt |
| 20 | `infra_list_hosts` | Infra | List SSH hosts |
| 21 | `infra_show_host` | Infra | Show host details |
| 22 | `infra_list_services` | Infra | List services |
| 23 | `infra_search` | Infra | Search infrastructure |
| 24 | `infra_add_host` | Infra | Add SSH host |
| 25 | `infra_add_service` | Infra | Add service to host |
| 26 | `note_save` | Notes | Save a note |
| 27 | `note_search` | Notes | Search notes |
| 28 | `note_show` | Notes | Show full note |
| 29 | `note_edit` | Notes | Edit a note |
| 30 | `note_delete` | Notes | Delete a note |
| 31 | `article_research` | Research | Research topic across CM |
