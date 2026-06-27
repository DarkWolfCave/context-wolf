# ContextWolf V5.1.0 - MCP Tools Reference

Complete reference for all 46 MCP tools exposed by ContextWolf. Intended for developers using these tools via Claude Code.

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

### `context_delete`

Delete a single context entry by ID. **Irreversible** - removes the action plus its content, metadata and relations. Requires an explicit entry ID; there is intentionally no delete-by-query to prevent accidental mass deletion. Context entries are not edited in place - to correct a wrong entry, delete it and `context_save` a corrected one.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `entry_id` | integer\|string | Yes | The single context entry ID to delete |

**Example:**

```
context_delete(entry_id=42)
# → Deleted entry #42 [decision] from 'context-wolf': ...
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

### `infra_edit_host`

Update fields of an existing SSH host. Only provided fields are changed.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `hostname` | string | Yes | Existing hostname |
| `ip` | string | No | New IP address |
| `port` | integer | No | New SSH port |
| `user` | string | No | New SSH user |
| `identity_file` | string | No | New SSH key path |
| `location` | string | No | Enum: `local`, `extern` |
| `provider` | string | No | New provider |
| `server_type` | string | No | New server type |
| `tags` | array[string] | No | Replace tags |
| `comment` | string | No | New comment |

### `infra_delete_host`

Delete an SSH host. By default fails if the host still has services attached.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `hostname` | string | Yes | - | Hostname to delete |
| `force` | boolean | No | false | If true, cascade-delete the host's services |

### `infra_edit_service`

Update fields of an existing service. Only provided fields are changed.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `hostname` | string | Yes | Host the service runs on |
| `service_name` | string | Yes | Service to edit |
| `env` | string | No | Enum: `prod`, `staging`, `dev`, `test` |
| `app_path` | string | No | New application path |
| `service_type` | string | No | New service type |
| `deploy_method` | string | No | New deploy method |
| `health_url` | string | No | New health check URL |
| `tags` | array[string] | No | Replace tags |
| `comment` | string | No | New comment |

### `infra_delete_service`

Delete a service from a host.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `hostname` | string | Yes | Host the service runs on |
| `service_name` | string | Yes | Service to delete |

**Example:**

```
infra_add_host(hostname="web-prod", ip="10.0.0.5", user="deploy", location="extern", provider="Hetzner")
infra_add_service(hostname="web-prod", service_name="myapp", env="prod", service_type="docker")
infra_list_hosts(location="extern")
infra_show_host(hostname="web-prod")
infra_edit_service(hostname="web-prod", service_name="myapp", health_url="https://web-prod/health")
infra_delete_host(hostname="old-staging", force=true)   # also removes its services
```

---

## Now (sprint backlog)

A curated cross-project shortlist of what's actively in flight. Three
active buckets (`today` / `week` / `later`) plus a 24h `done` holding
bucket. Each bucket has a configurable WIP limit (defaults 7 / 20 / 50)
so the list stays tight instead of accumulating like a generic TODO
list. Items can either stand alone or reference an existing CM entity;
the listing JOINs on the referenced table so callers see the live
status of the linked entity (e.g. a referenced TODO that has since been
closed).

### `now_add`

Add an item to the Now list. Refuses to add when the bucket's WIP limit
is reached - move or remove an existing item first.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `title` | string | Yes | - | Short, action-oriented title (max 200 chars) |
| `bucket` | string | No | `today` | Enum: `today`, `week`, `later` |
| `project` | string | No | - | Project name (cross-project is fine) |
| `link_type` | string | No | - | Optional CM entity type. Enum: `todo`, `action`, `note`, `snippet`, `ai_instruction`, `host`, `service` |
| `link_id` | integer\|string | No | - | ID of the linked entity (required when `link_type` is set) |

### `now_list`

List Now items ordered by bucket and position. Returns JSON `{items, counts, limits}`.
Each item carries a `linked` payload with live status when it references an
existing CM entity. `counts` is always returned for all four buckets so the UI
can render a capacity overview independently of any filter.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `bucket` | string | No | - | Filter by bucket. Enum: `today`, `week`, `later`, `done` |
| `project` | string | No | - | Filter by project |
| `include_done` | boolean | No | false | Include the `done` holding bucket |

### `now_show`

Show a single Now item including its linked-entity payload (if any).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `item_id` | integer\|string | Yes | Now item ID |

### `now_move`

Move an item between active buckets. Respects the target bucket's WIP limit.
Use `now_done` to finish an item (the `done` bucket cannot be a `now_move` target).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `item_id` | integer\|string | Yes | Now item ID |
| `to_bucket` | string | Yes | Enum: `today`, `week`, `later` |

### `now_edit`

Rename a Now item in place. Title-only by design: the bucket changes via
`now_move`, status via `now_done` / `now_remove`. Use this instead of
deleting and re-adding an item to fix a title - delete+re-add would reset
the item's position, creation time and linked-entity reference. The same
single-line 200-character title rule as `now_add` applies.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `item_id` | integer\|string | Yes | Now item ID |
| `title` | string | Yes | New title (max 200 chars, single-line) |

### `now_done`

Mark an item as done. It moves into the `done` holding bucket and is
hard-deleted automatically 24h later (lazy GC on the next `now_list` call).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `item_id` | integer\|string | Yes | Now item ID to complete |

### `now_remove`

Hard-delete a Now item. Use this to drop something off the list entirely
(rather than finishing it via `now_done`).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `item_id` | integer\|string | Yes | Now item ID to delete |

### `now_reorder`

Rewrite the order of items in a bucket (e.g. after drag-and-drop in the GUI).
`ordered_ids` must list every item currently in the bucket exactly once -
the call is rejected if the set doesn't match.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `bucket` | string | Yes | Enum: `today`, `week`, `later`, `done` |
| `ordered_ids` | array[integer] | Yes | Item IDs in the new order |

### `now_settings_get`

Return the current WIP limits for `today` / `week` / `later` as JSON.

*No parameters.*

### `now_settings_set`

Update one or more bucket WIP limits (range 1-100). Only provided values
are changed. Returns the resulting settings.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `today` | integer | No | New limit for `today` |
| `week` | integer | No | New limit for `week` |
| `later` | integer | No | New limit for `later` |

**Example:**

```
# A free-form item plus one that references an existing TODO
now_add(title="Fix DSGVO footer link", bucket="today", project="myapp")
now_add(title="Polish settings dialog", link_type="todo", link_id=42)

now_list()
# → JSON with items grouped by bucket, plus counts and limits.
#   The linked item shows the TODO's live status (open / done / cancelled).

now_move(item_id=5, to_bucket="week")
now_edit(item_id=5, title="Fix DSGVO footer link (impressum too)")  # rename in place
now_done(item_id=5)        # → moved to 'done', auto-purged after 24h
now_remove(item_id=7)      # → dropped entirely (not "finished")

now_settings_set(today=5)  # tighten the today bucket
```

### Response shape (now_list)

```json
{
  "items": [
    {
      "id": 5,
      "bucket": "today",
      "title": "Fix DSGVO footer link",
      "project": "myapp",
      "position": 0,
      "created_at": "2026-05-23T10:00:00",
      "moved_to_bucket_at": "2026-05-23T10:00:00",
      "done_at": null,
      "linked": null
    },
    {
      "id": 6,
      "bucket": "today",
      "title": "Polish settings dialog",
      "project": null,
      "position": 1,
      "linked": {
        "type": "todo",
        "id": 42,
        "exists": true,
        "status": "in_progress",
        "summary": "Settings dialog needs a save-confirmed toast",
        "closed_at": null
      }
    }
  ],
  "counts": { "today": 2, "week": 0, "later": 0, "done": 0 },
  "limits": { "today": 7, "week": 20, "later": 50 }
}
```

- `items` is sorted by `(bucket, position, id)` - render top-down without
  re-sorting.
- `linked: null` for free-form items.
- `linked.exists: false` when the referenced entity has been deleted - UI
  should flag it visually.

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
article_research(topic="authentication", project="myapp", days_back=30)

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
| 5 | `context_delete` | Context | Delete a single context entry |
| 6 | `snippet_search` | Snippets | Search code snippets |
| 7 | `snippet_show` | Snippets | Show full snippet |
| 8 | `snippet_add` | Snippets | Add a code snippet |
| 9 | `snippet_list` | Snippets | List all snippets |
| 10 | `todo_add` | TODO | Add a task |
| 11 | `todo_list` | TODO | List tasks |
| 12 | `todo_start` | TODO | Start a task |
| 13 | `todo_done` | TODO | Complete a task |
| 14 | `todo_show` | TODO | Show task details |
| 15 | `todo_reopen` | TODO | Reopen a task |
| 16 | `todo_cancel` | TODO | Cancel a task |
| 17 | `session` | Core | Show session info |
| 18 | `stats` | Core | Show project statistics |
| 19 | `projects` | Core | List all projects |
| 20 | `ai_prompt` | Core | Generate AI session prompt |
| 21 | `infra_list_hosts` | Infra | List SSH hosts |
| 22 | `infra_show_host` | Infra | Show host details |
| 23 | `infra_list_services` | Infra | List services |
| 24 | `infra_search` | Infra | Search infrastructure |
| 25 | `infra_add_host` | Infra | Add SSH host |
| 26 | `infra_add_service` | Infra | Add service to host |
| 27 | `infra_edit_host` | Infra | Update host fields |
| 28 | `infra_delete_host` | Infra | Delete a host |
| 29 | `infra_edit_service` | Infra | Update service fields |
| 30 | `infra_delete_service` | Infra | Delete a service |
| 31 | `note_save` | Notes | Save a note |
| 32 | `note_search` | Notes | Search notes |
| 33 | `note_show` | Notes | Show full note |
| 34 | `note_edit` | Notes | Edit a note |
| 35 | `note_delete` | Notes | Delete a note |
| 36 | `now_add` | Now | Add item to sprint backlog |
| 37 | `now_list` | Now | List items (returns JSON) |
| 38 | `now_show` | Now | Show single item with link payload |
| 39 | `now_move` | Now | Move item between buckets |
| 40 | `now_edit` | Now | Rename an item in place (title-only) |
| 41 | `now_done` | Now | Mark item done (24h holding) |
| 42 | `now_remove` | Now | Hard-delete an item |
| 43 | `now_reorder` | Now | Reorder items in a bucket |
| 44 | `now_settings_get` | Now | Read WIP limits |
| 45 | `now_settings_set` | Now | Update WIP limits |
| 46 | `article_research` | Research | Research topic across CM |
