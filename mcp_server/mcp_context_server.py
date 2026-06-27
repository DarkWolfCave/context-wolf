#!/usr/bin/env python3
"""
MCP Server for ContextWolf - Claude Code Integration
Provides direct integration with Claude Code via Model Context Protocol

Migrated to FastMCP (high-level API) from low-level Server API.
"""

import json
import logging
import sys
import time
import functools
from pathlib import Path
from typing import Optional, Union, Literal
from contextlib import asynccontextmanager
from pydantic import Field

from mcp.server.fastmcp import FastMCP, Context

# Import ContextWolf core
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.core.database import Database
from src.core.config import Config
from src.domain.actions import ActionManager
from src.domain.search import SearchManager
from src.domain.session import SessionManager
from src.features.snippets import SnippetManager
from src.features.todos import TodoManager
from src.features.ai_instructions import AIInstructionManager
from src.features.test_management import TestManager
from src.features.test_runner import TestRunner
from src.features.test_reporting import TestReporter
from src.features.smart_search import SmartSearchManager
from src.features.infrastructure import InfrastructureManager
from src.features.notes import NotesManager
from src.features.now import NowManager, NowLimitExceeded
from src.features.article_research import ArticleResearchManager
from src.version import __version__

# Configure logging
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("mcp-context")


# --- Lifespan: DB + Manager initialization/cleanup ---

@asynccontextmanager
async def lifespan(app: FastMCP):
    """Initialize database and managers on startup, cleanup on shutdown."""
    config = Config()
    db = Database(config=config)

    logger.info(f"ContextWolf MCP Server {__version__} starting...")
    logger.info(f"Backend: {config.database_backend.upper()}")

    managers = {
        "db": db,
        "config": config,
        "action_manager": ActionManager(db),
        "search_manager": SearchManager(db),
        "session_manager": SessionManager(db),
        "snippet_manager": SnippetManager(db),
        "todo_manager": TodoManager(db),
        "ai_instruction_manager": AIInstructionManager(db),
        "test_manager": TestManager(db),
        "test_runner": TestRunner(db),
        "test_reporter": TestReporter(db),
        "infrastructure_manager": InfrastructureManager(db),
        "notes_manager": NotesManager(db),
        "now_manager": NowManager(db),
    }
    managers["smart_search_manager"] = SmartSearchManager(
        db,
        ai_instruction_manager=managers["ai_instruction_manager"],
        snippet_manager=managers["snippet_manager"],
        search_manager=managers["search_manager"],
    )
    managers["article_research_manager"] = ArticleResearchManager(
        db,
        search_manager=managers["search_manager"],
        notes_manager=managers["notes_manager"],
    )

    yield managers

    # Shutdown
    logger.info("Cleaning up resources...")
    db.close()
    logger.info("Server shutdown complete")


# --- FastMCP Server ---

mcp = FastMCP(
    "context-wolf",
    lifespan=lifespan,
)


# --- Feature Detection: Pinned (GUI-only feature) ---
#
# Pinned items are curated in the optional GUI (context-wolf-ui). If the
# user has the GUI installed, the pinned_items table exists and we expose
# `pinned_list` as an MCP tool. Without the GUI the tool stays unregistered
# to keep the MCP schema lean.

def _pinned_tables_available() -> bool:
    """Quick one-shot DB check at import time. Own short-lived connection."""
    try:
        config = Config()
        db = Database(config=config)
        row = db.fetchone("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'pinned_items'
        """)
        db.close()
        return row is not None
    except Exception:
        return False


_PINNED_AVAILABLE = _pinned_tables_available()
if _PINNED_AVAILABLE:
    logger.info("Pinned feature detected (GUI tables present) - registering pinned_list tool")
else:
    logger.info("Pinned feature not available (no GUI tables) - skipping pinned_list tool")


# --- Tool-Usage Tracking Decorator ---

def tracked(func):
    """Decorator that logs tool usage to mcp_tool_usage table."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        success = True
        error_msg = None
        result = None
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            success = False
            error_msg = str(e)
            raise
        finally:
            try:
                ctx = kwargs.get("ctx")
                if ctx and hasattr(ctx, "request_context") and ctx.request_context:
                    duration_ms = (time.time() - start) * 1000
                    response_size = len(result) if isinstance(result, str) else 0
                    session_id = SessionManager.generate_session_id()
                    db = ctx.request_context.lifespan_context["db"]
                    db.execute(
                        "INSERT INTO mcp_tool_usage (tool_name, session_id, duration_ms, response_size_bytes, success, error) VALUES (?, ?, ?, ?, ?, ?)",
                        [func.__name__, session_id, duration_ms, response_size, success, error_msg],
                    )
                    db.commit()
            except Exception as tracking_error:
                logger.warning(f"Failed to track tool usage for {func.__name__}: {tracking_error}")
    return wrapper


def get_mgr(ctx: Context, name: str):
    """Helper to get a manager from lifespan context."""
    return ctx.request_context.lifespan_context[name]


# ========== CONTEXT MANAGEMENT (5 tools) ==========

@mcp.tool()
@tracked
def context_save(
    content: str = Field(description="What was done or decided"),
    type: Literal["code", "fix", "feature", "decision", "refactor", "test", "doc", "command"] = Field(default="general", description="Type of action"),
    project: Optional[str] = Field(default=None, description="Project name (recommended to specify, defaults to 'global' if not set)"),
    ctx: Context = None,
) -> str:
    """Save an action or decision to context manager. If no project specified, saves to 'global'."""
    am = get_mgr(ctx, "action_manager")
    actual_project = project or "global"
    no_project_warning = ""
    if not project:
        no_project_warning = "Warning: No project specified - saved under 'global'.\n   Tip: Use context_move(entry_id=ID, project=\"projectname\") to move it.\n"

    action_id = am.save(
        content=content,
        action_type=type,
        project=actual_project,
    )

    stale_warning = ""
    try:
        from src.core.embedding_health import check_and_mark_warned
        db = get_mgr(ctx, "db")
        msg = check_and_mark_warned(db)
        if msg:
            stale_warning = f"⚠️  {msg}\n"
    except Exception:
        pass

    return f"{stale_warning}{no_project_warning}Saved as action #{action_id}"


@mcp.tool()
@tracked
def context_move(
    entry_id: Union[int, str] = Field(description="The entry ID to move"),
    project: str = Field(description="Target project name"),
    ctx: Context = None,
) -> str:
    """Move a context entry to a different project."""
    am = get_mgr(ctx, "action_manager")
    result = am.move_entry(int(entry_id), project)
    if "error" in result:
        return result["error"]
    return f"Entry #{entry_id}: '{result['old_project']}' -> '{result['new_project']}'"


@mcp.tool()
@tracked
def context_search(
    query: str = Field(description="Search term"),
    type: Optional[str] = Field(default=None, description="Filter by type (optional)"),
    project: Optional[str] = Field(default="all", description="Project name or 'current' or 'all'"),
    limit: int = Field(default=20, description="Max results"),
    ctx: Context = None,
) -> str:
    """Search the context database."""
    sm = get_mgr(ctx, "search_manager")
    results = sm.search(query=query, type_filter=type, limit=limit, project=project)

    if not results:
        return f"No results found for '{query}'"

    response = [f"Found {len(results)} results:"]
    for r in results[:10]:
        response.append(f"ID {r['id']}: [{r['type']}] {r.get('snippet', r.get('summary', ''))}")
    response.append("\nUse context_show(entry_id=ID) for full content")
    return "\n".join(response)


@mcp.tool()
@tracked
def context_show(
    entry_id: Union[int, str] = Field(description="The context entry ID to show"),
    ctx: Context = None,
) -> str:
    """Show full content of a specific context entry by ID. Use after context_search to see complete details."""
    am = get_mgr(ctx, "action_manager")
    entry = am.get_entry(int(entry_id))
    if not entry:
        return f"Entry #{entry_id} not found"

    content_str = entry.get("content") or entry.get("summary", "No content")
    return (
        f"Entry #{entry['id']}: [{entry['type']}]\n"
        f"Project: {entry['project']} | Created: {entry.get('created_at', 'N/A')} | Session: {entry.get('session_id', 'N/A')}\n"
        f"{'=' * 40}\n"
        f"{content_str}"
    )


@mcp.tool()
@tracked
def context_delete(
    entry_id: Union[int, str] = Field(description="The single context entry ID to delete (deletes the action and its content/metadata/relations). No bulk or query-based deletion - one explicit ID at a time."),
    ctx: Context = None,
) -> str:
    """Delete a single context entry by ID. Irreversible: removes the action plus its content, metadata and relations. Requires an explicit entry ID - there is intentionally no delete-by-query to prevent accidental mass deletion. To fix a wrong entry, delete it and context_save a corrected one (context entries are not edited in place)."""
    am = get_mgr(ctx, "action_manager")
    entry = am.get_entry(int(entry_id))
    if not entry:
        return f"Entry #{entry_id} not found - nothing deleted"

    summary = (entry.get("content") or entry.get("summary") or "")[:60]
    am.delete_entry(int(entry_id), silent=True)
    return f"Deleted entry #{entry_id} [{entry['type']}] from '{entry['project']}': {summary}"


# ========== SNIPPET MANAGEMENT (4 tools) ==========

@mcp.tool()
@tracked
def snippet_search(
    query: Optional[str] = Field(default=None, description="Search term"),
    file_type: Optional[str] = Field(default=None, description="Filter by file type"),
    tags: Optional[list[str]] = Field(default=None, description="Filter by tags"),
    ctx: Context = None,
) -> str:
    """Search for code snippets."""
    sm = get_mgr(ctx, "snippet_manager")
    results = sm.search(query=query, file_type=file_type, tags=tags)

    if not results:
        return "No snippets found"

    response = [f"Found {len(results)} snippets:"]
    for s in results[:10]:
        response.append(f"ID {s.get('id')}: {s['name']} ({s.get('file_type', 'unknown')}) - {s.get('description', '')}")
    return "\n".join(response)


@mcp.tool()
@tracked
def snippet_show(
    snippet_id: Optional[Union[int, str]] = Field(default=None, description="Snippet ID"),
    name: Optional[str] = Field(default=None, description="Snippet name (alternative to ID)"),
    ctx: Context = None,
) -> str:
    """Show full content of a specific snippet."""
    sm = get_mgr(ctx, "snippet_manager")
    if snippet_id:
        snippet = sm.get_by_id(int(snippet_id), full_content=True)
    elif name:
        snippet = sm.get(name, full_content=True)
    else:
        return "Either snippet_id or name is required"

    if not snippet:
        return "Snippet not found"

    response = [f"{snippet.get('name', 'unnamed')} (ID #{snippet.get('id')})"]
    response.append(f"File: {snippet.get('file_path', 'N/A')}")
    response.append(f"Type: {snippet.get('file_type', 'unknown')}")
    response.append(f"\n{snippet.get('content', 'No content')}")
    return "\n".join(response)


@mcp.tool()
@tracked
def snippet_add(
    file_path: str = Field(description="Path to the file to add as snippet"),
    name: Optional[str] = Field(default=None, description="Name for the snippet (default: filename)"),
    description: Optional[str] = Field(default=None, description="Description of the snippet"),
    tags: Optional[list[str]] = Field(default=None, description="Tags for categorization"),
    store_content: bool = Field(default=False, description="Store full file content in DB (default: false)"),
    ctx: Context = None,
) -> str:
    """Add a code snippet or template to the database. Reads the file and stores metadata (path, type, description). Use store_content=true to store the full file content in the database."""
    sm = get_mgr(ctx, "snippet_manager")
    snippet_id = sm.add(
        file_path=file_path,
        name=name,
        description=description,
        tags=tags,
        store_content=store_content,
    )
    return f"Snippet #{snippet_id} added: {file_path}"


@mcp.tool()
@tracked
def snippet_list(
    limit: int = Field(default=100, description="Max results (default: 100)"),
    ctx: Context = None,
) -> str:
    """List all code snippets in the database."""
    sm = get_mgr(ctx, "snippet_manager")
    snippets = sm.list_all(limit=limit)
    if not snippets:
        return "No snippets found"
    lines = [f"Snippets ({len(snippets)}):"]
    for s in snippets:
        tags_str = f" [{s.get('tags', '')}]" if s.get('tags') else ""
        lines.append(f"  #{s['id']} {s.get('name', 'unnamed')} ({s.get('file_type', '?')}){tags_str}")
    return "\n".join(lines)


# ========== TODO MANAGEMENT (6 tools) ==========

@mcp.tool()
@tracked
def todo_add(
    content: str = Field(description="TODO content"),
    priority: Literal["high", "normal", "low"] = Field(default="normal", description="Priority level"),
    category: Optional[str] = Field(default=None, description="Category (optional)"),
    project: Optional[str] = Field(default=None, description="Project name (recommended to specify, defaults to 'default' if not set)"),
    ctx: Context = None,
) -> str:
    """Add a TODO task to track work. By default, TODOs are scoped to the current project (must specify project parameter)."""
    tm = get_mgr(ctx, "todo_manager")
    first_line = content.split("\n")[0].strip()
    summary = first_line[:200] if len(first_line) > 200 else first_line

    todo_id = tm.add_todo(
        summary=summary,
        content=content,
        priority=priority,
        category=category,
        project_name=project,
    )
    return f"TODO created (ID: {todo_id})"


@mcp.tool()
@tracked
def todo_list(
    status: Optional[Literal["open", "in_progress", "done", "cancelled"]] = Field(default="open", description="Filter by status"),
    priority: Optional[Literal["high", "normal", "low"]] = Field(default=None, description="Filter by priority"),
    scope: Literal["project", "all"] = Field(default="project", description="Scope: 'project' for current project TODOs (default), 'all' for all projects"),
    project: Optional[str] = Field(default=None, description="Project name (required when scope='project', ignored when scope='all')"),
    ctx: Context = None,
) -> str:
    """List TODO tasks. Default scope is 'project' which shows TODOs for current project only (must specify project parameter). Use scope='all' to see all TODOs across all projects."""
    tm = get_mgr(ctx, "todo_manager")

    if scope == "project" and not project:
        return "Error: 'project' parameter required when scope='project'. Use scope='all' to see all TODOs across all projects."

    effective_project = None if scope == "all" else project
    todos = tm.list_todos(status=status, priority=priority, project_name=effective_project)

    if not todos:
        scope_msg = f" for project '{project}'" if effective_project else " (all projects)"
        return f"No TODOs found{scope_msg}"

    response = [f"TODOs ({len(todos)} entries):"]
    for t in todos[:20]:
        status_icon = {"open": "o", "in_progress": ">", "done": "x"}.get(t["status"], "?")
        priority_icon = {"high": "!", "normal": "-", "low": "."}.get(t.get("priority"), "-")
        response.append(f"[{status_icon}] #{t['id']} [{priority_icon}] {t['summary']}")

    if len(todos) > 20:
        response.append(f"\n... and {len(todos) - 20} more TODOs")
    return "\n".join(response)


@mcp.tool()
@tracked
def todo_show(
    todo_id: Union[int, str] = Field(description="TODO ID to show"),
    ctx: Context = None,
) -> str:
    """Show details of a specific TODO by ID."""
    tm = get_mgr(ctx, "todo_manager")
    todos = tm.list_todos(include_done=True, limit=1000)
    todo = None
    for t in todos:
        if t["id"] == int(todo_id):
            todo = t
            break
    if not todo:
        return f"TODO #{todo_id} not found"

    lines = [f"TODO #{todo['id']}: {todo.get('summary', '')}"]
    lines.append(f"Status: {todo.get('status', '?')} | Priority: {todo.get('priority', '?')}")
    if todo.get("category"):
        lines.append(f"Category: {todo['category']}")
    if todo.get("project"):
        lines.append(f"Project: {todo['project']}")
    if todo.get("content"):
        lines.append(f"\n{todo['content']}")
    return "\n".join(lines)


@mcp.tool()
@tracked
def todo_start(
    todo_id: Union[int, str] = Field(description="TODO ID to start"),
    ctx: Context = None,
) -> str:
    """Start working on a TODO task."""
    tm = get_mgr(ctx, "todo_manager")
    tm.update_status(int(todo_id), "in_progress")
    return f"TODO #{todo_id} in progress"


@mcp.tool()
@tracked
def todo_done(
    todo_id: Union[int, str] = Field(description="TODO ID to complete"),
    ctx: Context = None,
) -> str:
    """Mark a TODO task as done."""
    tm = get_mgr(ctx, "todo_manager")
    tm.mark_done([int(todo_id)])
    return f"Done: {todo_id}"


@mcp.tool()
@tracked
def todo_reopen(
    todo_id: Union[int, str] = Field(description="TODO ID to reopen"),
    ctx: Context = None,
) -> str:
    """Reopen a completed or cancelled TODO task."""
    tm = get_mgr(ctx, "todo_manager")
    result = tm.reopen([int(todo_id)])
    if result.get("success") and int(todo_id) in result["success"]:
        return f"TODO #{todo_id} reopened"
    failed = result.get("failed", [])
    reason = failed[0].get("reason", "unknown") if failed else "unknown"
    return f"Could not reopen TODO #{todo_id}: {reason}"


@mcp.tool()
@tracked
def todo_cancel(
    todo_id: Union[int, str] = Field(description="TODO ID to cancel"),
    ctx: Context = None,
) -> str:
    """Cancel a TODO task."""
    tm = get_mgr(ctx, "todo_manager")
    success = tm.update_status(int(todo_id), "cancelled")
    if success:
        return f"TODO #{todo_id} cancelled"
    return f"Could not cancel TODO #{todo_id}"


# ========== CORE UTILITIES (4 tools) ==========

@mcp.tool()
@tracked
def session(
    session_id: Optional[str] = Field(default=None, description="Session ID (optional, default: current)"),
    verbose: bool = Field(default=False, description="Show detailed output"),
    ctx: Context = None,
) -> str:
    """Show current session or specific session."""
    sm = get_mgr(ctx, "session_manager")
    session_data = sm.get_session(session_id=session_id)
    return json.dumps(session_data, indent=2, default=str)


@mcp.tool()
@tracked
def stats(
    project: Optional[str] = Field(default=None, description="Project name (optional)"),
    ctx: Context = None,
) -> str:
    """Show project statistics."""
    from src.features.stats import StatsManager
    db = get_mgr(ctx, "db")
    stats_mgr = StatsManager(db)
    stats_data = stats_mgr.get_stats(project_name=project)
    return json.dumps(stats_data, indent=2, default=str)


@mcp.tool()
@tracked
def projects(ctx: Context = None) -> str:
    """List all projects with statistics."""
    sm = get_mgr(ctx, "search_manager")
    project_list = sm.list_projects()
    response = [f"Projects ({len(project_list)}):"]
    for p in project_list:
        project_name = p.get("name", "unnamed")
        action_count = p.get("action_count", 0)
        response.append(f"  {project_name}: {action_count} entries")
    return "\n".join(response)


@mcp.tool()
@tracked
def ai_prompt(
    quick: bool = Field(default=False, description="Quick mode (less verbose)"),
    verbose: bool = Field(default=False, description="Verbose mode (more details)"),
    smart: bool = Field(default=False, description="Smart mode: Session-aware context filtering (reduces tokens by analyzing recent work)"),
    hours: int = Field(default=24, description="Hours to look back for session analysis (default: 24, only for smart mode)"),
    ctx: Context = None,
) -> str:
    """Generate AI session prompt with current context. Smart mode uses session-aware filtering to reduce token usage by ~8-55% while maintaining relevance."""
    from src.features.ai_prompt import AIPromptManager
    ai_prompt_mgr = AIPromptManager(
        get_mgr(ctx, "search_manager"),
        get_mgr(ctx, "session_manager"),
        get_mgr(ctx, "snippet_manager"),
        get_mgr(ctx, "ai_instruction_manager"),
    )
    if quick:
        return ai_prompt_mgr.generate_quick_start()
    return ai_prompt_mgr.generate_session_prompt(verbose=verbose, smart=smart, hours=hours)


# ========== PINNED (conditional - only when GUI tables exist) ==========

if _PINNED_AVAILABLE:
    @mcp.tool()
    @tracked
    def pinned_list(
        project: Optional[str] = Field(default=None, description="Optional project filter. Without project: all pinned items. With project: global items + items scoped to that project."),
        ctx: Context = None,
    ) -> str:
        """List pinned items curated in the context-wolf-ui GUI (notes, snippets, actions, ai_instructions). Read-only; pinning is done in the GUI. Returns Markdown output grouped by item type."""
        from src.features.pinned import PinnedManager
        db = get_mgr(ctx, "db")
        pinned_mgr = PinnedManager(db)
        return pinned_mgr.export_markdown(project=project)


# ========== INFRASTRUCTURE MANAGEMENT (5 tools) ==========

@mcp.tool()
@tracked
def infra_list_hosts(
    scope: Optional[Literal["global", "project"]] = Field(default=None, description="Filter by scope: 'global' shows hosts from all projects, 'project' shows only current project hosts"),
    location: Optional[Literal["local", "extern"]] = Field(default=None, description="Filter by location: 'local' for local network (LAN), 'extern' for external internet servers"),
    project_name: Optional[str] = Field(default=None, description="Filter by specific project name (only when scope='project')"),
    minimal: bool = Field(default=True, description="Return minimal output (default: true) for token efficiency. Set to false for full host details."),
    ctx: Context = None,
) -> str:
    """List infrastructure SSH hosts with optional filtering. Returns minimal output by default (hostname, location, server_type, provider) for token efficiency. Use infra_show_host for detailed info."""
    im = get_mgr(ctx, "infrastructure_manager")
    hosts = im.list_hosts(scope=scope, location=location, project_name=project_name, minimal=minimal)
    if not hosts:
        return "No hosts found"

    response = [f"SSH Hosts ({len(hosts)}):"]
    for host in hosts:
        tags_str = ",".join(host.get("tags", [])) if host.get("tags") else ""
        if minimal:
            response.append(f"  - {host['hostname']} ({host.get('location', 'N/A')}) - {host.get('server_type', '')} [{tags_str}]")
        else:
            response.append(f"  - {host['hostname']} ({host.get('location', 'N/A')}) - {host.get('server_type', '')} [{tags_str}]")
            if host.get("ip"):
                response.append(f"    SSH: ssh {host['hostname']}  (use this command)")
                response.append(f"    Connection: {host.get('user', 'N/A')}@{host['ip']}:{host.get('port', 22)}")
            if host.get("identity_file"):
                response.append(f"    Identity: {host['identity_file']}")
            if host.get("provider"):
                response.append(f"    Provider: {host['provider']}")
            if host.get("comment"):
                response.append(f"    Comment: {host['comment']}")
    return "\n".join(response)


@mcp.tool()
@tracked
def infra_show_host(
    hostname: str = Field(description="The hostname to show details for (e.g., 'prod-server-01', 'db-host')"),
    ctx: Context = None,
) -> str:
    """Show detailed information about a specific SSH host including all connection details (IP, port, user, SSH key path) and all services running on it. Use this when you need complete info about ONE specific host."""
    im = get_mgr(ctx, "infrastructure_manager")
    host = im.show_host(hostname)
    if not host:
        return f"Host '{hostname}' not found"

    response = [f"Host: {host['hostname']}"]
    response.append(f"SSH Access: ssh {host['hostname']}  (use this command)")
    if host.get("ip"):
        response.append(f"Connection Info: {host['user']}@{host['ip']}:{host.get('port', 22)}  (informational only)")
    response.append(f"Location: {host.get('location', 'N/A')} | Provider: {host.get('provider', 'N/A')}")
    response.append(f"Type: {host.get('server_type', 'N/A')} | Scope: {host['scope']}")

    if host.get("services"):
        response.append(f"\nServices ({len(host['services'])}):")
        for svc in host["services"]:
            env_str = f"[{svc['env']}]" if svc.get("env") else ""
            deploy_method = svc.get("deploy_method")
            deploy_str = ""
            if deploy_method == "ssh":
                deploy_str = " [SSH]"
            elif deploy_method == "local":
                deploy_str = " [local]"
            elif deploy_method:
                deploy_str = f" [{deploy_method}]"

            response.append(f"  - {svc['service_name']} {env_str}{deploy_str} -> {svc.get('app_path', 'N/A')}")
            if svc.get("service_type"):
                response.append(f"    Type: {svc['service_type']}")
            if svc.get("tags"):
                try:
                    tags_list = json.loads(svc["tags"]) if isinstance(svc["tags"], str) else svc["tags"]
                    if tags_list:
                        response.append(f"    Tags: {', '.join(tags_list)}")
                except Exception:
                    pass
            if svc.get("comment"):
                response.append(f"    Deploy: {svc['comment']}")
    return "\n".join(response)


@mcp.tool()
@tracked
def infra_list_services(
    hostname: Optional[str] = Field(default=None, description="Filter by hostname: show only services running on this specific host"),
    env: Optional[Literal["prod", "staging", "dev", "test"]] = Field(default=None, description="Filter by environment"),
    scope: Optional[Literal["global", "project"]] = Field(default=None, description="Filter by scope"),
    project_name: Optional[str] = Field(default=None, description="Filter by specific project name"),
    ctx: Context = None,
) -> str:
    """List services/applications running on infrastructure hosts. CRITICAL: Always check deploy_method first - 'ssh' means execute via SSH on remote host, 'local' means execute locally."""
    im = get_mgr(ctx, "infrastructure_manager")
    services = im.list_services(hostname=hostname, env=env, scope=scope, project_name=project_name)
    if not services:
        return "No services found"

    response = [f"Services ({len(services)}):"]
    for svc in services:
        env_str = f"[{svc.get('env', '')}]" if svc.get("env") else ""
        deploy_method = svc.get("deploy_method")
        deploy_str = ""
        if deploy_method == "ssh":
            deploy_str = " [SSH]"
        elif deploy_method == "local":
            deploy_str = " [local]"
        elif deploy_method:
            deploy_str = f" [{deploy_method}]"
        response.append(f"  - {svc['service_name']} {env_str} on {svc['hostname']}{deploy_str} -> {svc.get('app_path', 'N/A')}")
    return "\n".join(response)


@mcp.tool()
@tracked
def infra_search(
    query: str = Field(description="Search term (e.g., 'gitea', 'token', 'telegraf', 'docker')"),
    limit: int = Field(default=5, description="Max results per category (default: 5)"),
    ctx: Context = None,
) -> str:
    """Search infrastructure hosts and services. Use this to find specific servers, services, or configuration details. Searches across: hostname, service_name, comment, tags, server_type, service_type."""
    im = get_mgr(ctx, "infrastructure_manager")
    results = im.search(query=query, limit=limit)

    hosts = results.get("hosts", [])
    services = results.get("services", [])

    if not hosts and not services:
        return f"No infrastructure found for '{query}'"

    response = [f"Infrastructure Search: '{query}'"]
    if hosts:
        response.append(f"\nHosts ({len(hosts)}):")
        for h in hosts:
            response.append(f"  - {h['hostname']} ({h.get('location', 'N/A')}) - {h.get('server_type', '')}")
            if h.get("comment"):
                comment = h["comment"][:80] + "..." if len(h["comment"]) > 80 else h["comment"]
                response.append(f"    -> {comment}")

    if services:
        response.append(f"\nServices ({len(services)}):")
        for s in services:
            env_str = f"[{s.get('env', '')}]" if s.get("env") else ""
            response.append(f"  - {s['service_name']} {env_str} on {s['hostname']}")
            if s.get("comment"):
                comment = s["comment"][:80] + "..." if len(s["comment"]) > 80 else s["comment"]
                response.append(f"    -> {comment}")

    response.append("\nUse infra_show_host(hostname='...') for full details")
    return "\n".join(response)


@mcp.tool()
@tracked
def infra_add_host(
    hostname: str = Field(description="SSH hostname (e.g., 'prod-server-01', 'web-prod-01')"),
    ip: Optional[str] = Field(default=None, description="IP address"),
    port: int = Field(default=22, description="SSH port (default: 22)"),
    user: Optional[str] = Field(default=None, description="SSH user"),
    identity_file: Optional[str] = Field(default=None, description="Path to SSH key (e.g., '~/.ssh/my-key')"),
    location: Optional[Literal["local", "extern"]] = Field(default=None, description="Location: 'local' for LAN, 'extern' for internet"),
    provider: Optional[str] = Field(default=None, description="Provider (e.g., 'Netcup', 'Hetzner', 'AWS')"),
    server_type: Optional[str] = Field(default=None, description="Server type (e.g., 'VPS', 'Dedicated', 'Raspberry Pi')"),
    scope: Literal["global", "project"] = Field(default="global", description="Scope: 'global' (all projects) or 'project'"),
    project_name: Optional[str] = Field(default=None, description="Project name (only when scope='project')"),
    tags: Optional[list[str]] = Field(default=None, description="Tags for categorization"),
    comment: Optional[str] = Field(default=None, description="Comment or description"),
    ctx: Context = None,
) -> str:
    """Add a new SSH host to infrastructure management."""
    im = get_mgr(ctx, "infrastructure_manager")
    host_id = im.add_host(
        hostname=hostname, ip=ip, port=port, user=user, identity_file=identity_file,
        location=location, provider=provider, server_type=server_type,
        scope=scope, project_name=project_name, tags=tags, comment=comment,
    )
    return f"Host '{hostname}' added (ID: {host_id})"


@mcp.tool()
@tracked
def infra_add_service(
    hostname: str = Field(description="Host where the service runs (must exist)"),
    service_name: str = Field(description="Service name (e.g., 'my-webapp', 'grafana')"),
    env: Optional[Literal["prod", "staging", "dev", "test"]] = Field(default=None, description="Environment"),
    app_path: Optional[str] = Field(default=None, description="Application path on host"),
    service_type: Optional[str] = Field(default=None, description="Service type (e.g., 'docker', 'systemd', 'pm2')"),
    deploy_method: Optional[str] = Field(default=None, description="Deployment method (e.g., 'ssh', 'local', 'docker compose')"),
    project_name: Optional[str] = Field(default=None, description="Project name to associate with"),
    tags: Optional[list[str]] = Field(default=None, description="Tags for categorization"),
    comment: Optional[str] = Field(default=None, description="Comment or description"),
    ctx: Context = None,
) -> str:
    """Add a service/application to an existing infrastructure host."""
    im = get_mgr(ctx, "infrastructure_manager")
    scope = "global" if not project_name else "project"
    service_id = im.add_service(
        hostname=hostname, service_name=service_name, env=env, app_path=app_path,
        service_type=service_type, deploy_method=deploy_method,
        scope=scope, project_name=project_name, tags=tags, comment=comment,
    )
    return f"Service '{service_name}' added to {hostname} (ID: {service_id})"


# ========== INFRASTRUCTURE EDIT/DELETE (4 tools) ==========

@mcp.tool()
@tracked
def infra_edit_host(
    hostname: str = Field(description="SSH hostname to edit (must exist)"),
    ip: Optional[str] = Field(default=None, description="IP address"),
    port: Optional[int] = Field(default=None, description="SSH port"),
    user: Optional[str] = Field(default=None, description="SSH user"),
    identity_file: Optional[str] = Field(default=None, description="Path to SSH key (e.g., '~/.ssh/my-key')"),
    location: Optional[Literal["local", "extern"]] = Field(default=None, description="Location: 'local' for LAN, 'extern' for internet"),
    provider: Optional[str] = Field(default=None, description="Provider (e.g., 'Netcup', 'Hetzner', 'AWS')"),
    server_type: Optional[str] = Field(default=None, description="Server type (e.g., 'VPS', 'Dedicated', 'Raspberry Pi')"),
    tags: Optional[list[str]] = Field(default=None, description="Tags for categorization (replaces existing tags)"),
    comment: Optional[str] = Field(default=None, description="Comment or description"),
    ctx: Context = None,
) -> str:
    """Edit an existing infrastructure host. Only provided fields are updated."""
    im = get_mgr(ctx, "infrastructure_manager")
    updated = im.edit_host(
        hostname=hostname, ip=ip, port=port, user=user, identity_file=identity_file,
        location=location, provider=provider, server_type=server_type,
        tags=tags, comment=comment,
    )
    if updated:
        return f"Host '{hostname}' updated"
    return f"Host '{hostname}' not found or no fields to update"


@mcp.tool()
@tracked
def infra_delete_host(
    hostname: str = Field(description="SSH hostname to delete"),
    force: bool = Field(default=False, description="Force deletion even if services exist (CASCADE deletes all services)"),
    ctx: Context = None,
) -> str:
    """Delete an infrastructure host. Use force=True to also delete all associated services."""
    im = get_mgr(ctx, "infrastructure_manager")
    _success, message = im.delete_host(hostname=hostname, force=force)
    return message


@mcp.tool()
@tracked
def infra_edit_service(
    hostname: str = Field(description="Host where the service runs"),
    service_name: str = Field(description="Service name to edit (must exist on the host)"),
    env: Optional[Literal["prod", "staging", "dev", "test"]] = Field(default=None, description="Environment"),
    app_path: Optional[str] = Field(default=None, description="Application path on host"),
    service_type: Optional[str] = Field(default=None, description="Service type (e.g., 'docker', 'systemd', 'pm2')"),
    deploy_method: Optional[str] = Field(default=None, description="Deployment method (e.g., 'ssh', 'local', 'docker compose')"),
    health_url: Optional[str] = Field(default=None, description="Health check URL"),
    tags: Optional[list[str]] = Field(default=None, description="Tags for categorization (replaces existing tags)"),
    comment: Optional[str] = Field(default=None, description="Comment or description"),
    ctx: Context = None,
) -> str:
    """Edit an existing service on an infrastructure host. Only provided fields are updated."""
    im = get_mgr(ctx, "infrastructure_manager")
    updated = im.edit_service(
        hostname=hostname, service_name=service_name, env=env, app_path=app_path,
        service_type=service_type, deploy_method=deploy_method,
        health_url=health_url, tags=tags, comment=comment,
    )
    if updated:
        return f"Service '{service_name}' on '{hostname}' updated"
    return f"Service '{service_name}' not found on '{hostname}' or no fields to update"


@mcp.tool()
@tracked
def infra_delete_service(
    hostname: str = Field(description="Host where the service runs"),
    service_name: str = Field(description="Service name to delete"),
    ctx: Context = None,
) -> str:
    """Delete a service from an infrastructure host."""
    im = get_mgr(ctx, "infrastructure_manager")
    _success, message = im.delete_service(hostname=hostname, service_name=service_name)
    return message


# ========== NOTES (5 tools) ==========

@mcp.tool()
@tracked
def note_save(
    title: str = Field(description="Note title (max 200 chars)"),
    content: str = Field(description="Markdown content of the note"),
    project: Optional[str] = Field(default=None, description="Project name to associate with (recommended)"),
    tags: Optional[str] = Field(default=None, description="Comma-separated tags (e.g., 'migration, domains, planung')"),
    ctx: Context = None,
) -> str:
    """Save a project note (Markdown). Use this to persist structured knowledge documents like migration plans, architecture decisions, domain configurations, pricing comparisons, or technical reference material. NOT for session documentation (use context_save for that)."""
    nm = get_mgr(ctx, "notes_manager")
    note_id = nm.add_note(title=title, content=content, project_name=project, tags=tags or "")
    project_info = f" in project '{project}'" if project else ""
    tags_info = f"\nTags: {tags}" if tags else ""
    return (
        f"Note saved as #{note_id}{project_info}{tags_info}\n"
        f"Title: {title}\n"
        f"Content: {len(content)} chars"
    )


@mcp.tool()
@tracked
def note_search(
    query: Optional[str] = Field(default=None, description="Search term (searches title, content, tags)"),
    project: Optional[str] = Field(default=None, description="Filter by project name"),
    tags: Optional[str] = Field(default=None, description="Filter by tag"),
    limit: int = Field(default=20, description="Max results (default: 20)"),
    ctx: Context = None,
) -> str:
    """Search project notes by keyword, project, or tags. Returns matching notes with content preview."""
    nm = get_mgr(ctx, "notes_manager")
    notes = nm.search_notes(query=query, project_name=project, tags=tags, limit=limit)

    if not notes:
        return "No notes found"

    response = [f"Notes ({len(notes)} found):"]
    for n in notes:
        project_str = f" [{n['project']}]" if n.get("project") else ""
        tags_str = f" #{n['tags']}" if n.get("tags") else ""
        preview = (n.get("content_preview", "") or "")[:100].replace("\n", " ")
        response.append(
            f"\n  #{n['id']}: {n['title']}{project_str}{tags_str}"
            f"\n     {preview}..."
            f"\n     ({n.get('content_length', 0)} chars, updated: {n.get('updated_at', 'N/A')})"
        )
    return "\n".join(response)


@mcp.tool()
@tracked
def note_show(
    note_id: Union[int, str] = Field(description="Note ID to show"),
    ctx: Context = None,
) -> str:
    """Show full content of a specific note by ID."""
    nm = get_mgr(ctx, "notes_manager")
    note = nm.get_note(int(note_id))
    if not note:
        return f"Note #{note_id} not found"

    project_str = f"Project: {note['project']}" if note.get("project") else "No project"
    tags_str = f"Tags: {note['tags']}" if note.get("tags") else ""
    return (
        f"Note #{note['id']}: {note['title']}\n"
        f"{project_str} | Created: {note.get('created_at', 'N/A')} | Updated: {note.get('updated_at', 'N/A')}\n"
        f"{tags_str}\n"
        f"{'=' * 40}\n"
        f"{note['content']}"
    )


@mcp.tool()
@tracked
def note_edit(
    note_id: Union[int, str] = Field(description="Note ID to edit"),
    title: Optional[str] = Field(default=None, description="New title (optional, max 200 chars)"),
    content: Optional[str] = Field(default=None, description="New Markdown content - replaces existing (optional)"),
    append: Optional[str] = Field(default=None, description="Text to append to existing content (optional, alternative to content)"),
    tags: Optional[str] = Field(default=None, description="New comma-separated tags (optional)"),
    ctx: Context = None,
) -> str:
    """Edit an existing note. Update title, content, and/or tags without deleting and recreating. Only provided fields are updated. Use 'append' to add text to existing content without replacing it."""
    nm = get_mgr(ctx, "notes_manager")
    nid = int(note_id)

    effective_content = content
    if append:
        existing = nm.get_note(nid)
        if not existing:
            return f"Note #{note_id} not found"
        effective_content = existing["content"] + "\n" + append

    updated = nm.update_note(note_id=nid, title=title, content=effective_content, tags=tags)
    if not updated:
        return f"Note #{note_id}: nothing to update (no fields provided)"

    changed = []
    if title is not None:
        changed.append("title")
    if append:
        changed.append(f"appended ({len(append)} chars)")
    elif content is not None:
        changed.append(f"content ({len(content)} chars)")
    if tags is not None:
        changed.append(f"tags -> {tags}")
    return f"Note #{note_id} updated: {', '.join(changed)}"


@mcp.tool()
@tracked
def note_delete(
    note_id: Union[int, str] = Field(description="Note ID to delete"),
    ctx: Context = None,
) -> str:
    """Delete a note by ID."""
    nm = get_mgr(ctx, "notes_manager")
    nm.delete_note(int(note_id))
    return f"Note #{note_id} deleted"


# ========== NOW (sprint backlog, 9 tools) ==========
#
# "Now" is a tight cross-project shortlist of what the user is actively
# working on. Items live in three active buckets (today/week/later) plus
# a short-lived `done` holding bucket. Each bucket has a WIP limit; the
# `done` bucket is auto-purged after 24h on the next list call.
#
# Items may either be free-form or reference an existing CM entity
# (todo, action, note, snippet, ai_instruction, host, service). When
# listed, the manager JOINs on the referenced table so callers see the
# live status of the linked entity.

_NOW_LINK_LITERAL = Literal[
    "todo", "action", "note", "snippet", "ai_instruction", "host", "service"
]
_NOW_BUCKET_ACTIVE = Literal["today", "week", "later"]
_NOW_BUCKET_ANY = Literal["today", "week", "later", "done"]


@mcp.tool()
@tracked
def now_add(
    title: str = Field(description="Short, action-oriented title (max 200 chars)"),
    bucket: _NOW_BUCKET_ACTIVE = Field(default="today", description="Target bucket: today / week / later"),
    project: Optional[str] = Field(default=None, description="Project name (optional, cross-project is fine)"),
    link_type: Optional[_NOW_LINK_LITERAL] = Field(default=None, description="Optional: existing CM entity type this item references"),
    link_id: Optional[Union[int, str]] = Field(default=None, description="Optional: ID of the linked entity. Required when link_type is set."),
    ctx: Context = None,
) -> str:
    """Add an item to the cross-project Now list. Refuses to add when the bucket's WIP limit is reached - demote or remove an existing item first."""
    nm = get_mgr(ctx, "now_manager")
    try:
        item_id = nm.add_item(
            title=title,
            bucket=bucket,
            project_name=project,
            linked_type=link_type,
            linked_id=int(link_id) if link_id is not None else None,
        )
    except NowLimitExceeded as e:
        return (
            f"Bucket '{e.bucket}' is full ({e.current}/{e.limit}). "
            "Move or remove an existing item before adding a new one."
        )
    link_info = f" -> {link_type}#{link_id}" if link_type else ""
    project_info = f" [{project}]" if project else ""
    return f"Now item #{item_id} added to '{bucket}'{project_info}{link_info}"


@mcp.tool()
@tracked
def now_list(
    bucket: Optional[_NOW_BUCKET_ANY] = Field(default=None, description="Filter by bucket (omit to see all active buckets)"),
    project: Optional[str] = Field(default=None, description="Filter by project"),
    include_done: bool = Field(default=False, description="Include the 'done' holding bucket"),
    ctx: Context = None,
) -> str:
    """List Now items, ordered by bucket and position. Returns JSON: {items, counts, limits}. Each item carries a `linked` payload with live status when it references an existing CM entity."""
    nm = get_mgr(ctx, "now_manager")
    data = nm.list_items(bucket=bucket, project_name=project, include_done=include_done)
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
@tracked
def now_show(
    item_id: Union[int, str] = Field(description="Now item ID"),
    ctx: Context = None,
) -> str:
    """Show a single Now item including its linked-entity payload (if any)."""
    nm = get_mgr(ctx, "now_manager")
    item = nm.get_item(int(item_id))
    if not item:
        return f"Now item #{item_id} not found"
    return json.dumps(item, indent=2, default=str)


@mcp.tool()
@tracked
def now_move(
    item_id: Union[int, str] = Field(description="Now item ID"),
    to_bucket: _NOW_BUCKET_ACTIVE = Field(description="Target bucket (today / week / later). Use now_done() to finish an item."),
    ctx: Context = None,
) -> str:
    """Move a Now item between active buckets. Respects the target bucket's WIP limit."""
    nm = get_mgr(ctx, "now_manager")
    try:
        result = nm.move_item(int(item_id), to_bucket)
    except NowLimitExceeded as e:
        return (
            f"Bucket '{e.bucket}' is full ({e.current}/{e.limit}). "
            "Move or remove an existing item before moving another into it."
        )
    if not result.get("moved"):
        return f"Now item #{item_id} already in '{to_bucket}'"
    return f"Now item #{item_id}: {result['from']} -> {result['bucket']}"


@mcp.tool()
@tracked
def now_edit(
    item_id: Union[int, str] = Field(description="Now item ID"),
    title: str = Field(description="New title (max 200 chars, single-line)"),
    ctx: Context = None,
) -> str:
    """Rename a Now item in place. Title-only: use now_move for the bucket and now_done/now_remove for status. Avoids the delete+re-add workaround, which would reset position, created_at and the linked-entity reference."""
    nm = get_mgr(ctx, "now_manager")
    try:
        result = nm.edit_title(int(item_id), title)
    except ValueError as e:
        return f"{e}"
    return f"Now item #{item_id} renamed: {result['title']}"


@mcp.tool()
@tracked
def now_done(
    item_id: Union[int, str] = Field(description="Now item ID to mark as done"),
    ctx: Context = None,
) -> str:
    """Mark a Now item as done. It moves into the 'done' holding bucket and is purged automatically after 24h."""
    nm = get_mgr(ctx, "now_manager")
    nm.mark_done(int(item_id))
    return f"Now item #{item_id} marked done"


@mcp.tool()
@tracked
def now_remove(
    item_id: Union[int, str] = Field(description="Now item ID to delete"),
    ctx: Context = None,
) -> str:
    """Hard-delete a Now item. Use this to kick something off the list entirely (instead of finishing it via now_done)."""
    nm = get_mgr(ctx, "now_manager")
    nm.remove_item(int(item_id))
    return f"Now item #{item_id} removed"


@mcp.tool()
@tracked
def now_reorder(
    bucket: _NOW_BUCKET_ANY = Field(description="Bucket to reorder"),
    ordered_ids: list[int] = Field(description="Item IDs in the new order. Must list every item currently in the bucket exactly once."),
    ctx: Context = None,
) -> str:
    """Rewrite the order of items in a bucket (e.g. after drag&drop). ordered_ids must match the bucket's current contents exactly."""
    nm = get_mgr(ctx, "now_manager")
    count = nm.reorder_bucket(bucket, ordered_ids)
    return f"Reordered {count} items in '{bucket}'"


@mcp.tool()
@tracked
def now_settings_get(ctx: Context = None) -> str:
    """Return the current WIP limits for today / week / later as JSON."""
    nm = get_mgr(ctx, "now_manager")
    return json.dumps(nm.get_settings(), indent=2)


@mcp.tool()
@tracked
def now_settings_set(
    today: Optional[int] = Field(default=None, description="New WIP limit for 'today' (1-100)"),
    week: Optional[int] = Field(default=None, description="New WIP limit for 'week' (1-100)"),
    later: Optional[int] = Field(default=None, description="New WIP limit for 'later' (1-100)"),
    ctx: Context = None,
) -> str:
    """Update one or more bucket WIP limits. Only provided values are changed. Returns the resulting settings."""
    nm = get_mgr(ctx, "now_manager")
    new_settings = nm.update_settings(today=today, week=week, later=later)
    return json.dumps(new_settings, indent=2)


# ========== ARTICLE RESEARCH (1 tool) ==========

@mcp.tool()
@tracked
def article_research(
    topic: str = Field(description="Research topic (e.g., 'PostgreSQL Migration', 'Docker Backup', 'Authentication')"),
    queries: Optional[list[str]] = Field(default=None, description="Optional: explicit search queries (default: auto-expanded from topic)"),
    project: Optional[str] = Field(default=None, description="Filter by project (default: cross-project search across all)"),
    days_back: Optional[int] = Field(default=None, description="Limit to last N days (default: all time)"),
    save_as_note: bool = Field(default=False, description="Save the dossier as a CM note (default: false)"),
    note_project: Optional[str] = Field(default=None, description="Project for saved note (only used with save_as_note)"),
    ctx: Context = None,
) -> str:
    """Research a topic across all CM entries. Creates a structured dossier with chronological clusters, type grouping, and pattern detection."""
    arm = get_mgr(ctx, "article_research_manager")
    return arm.research(
        topic=topic, queries=queries, project=project,
        days_back=days_back, save_as_note=save_as_note, note_project=note_project,
    )


# ========== RESOURCES ==========

@mcp.resource("context://session/current")
def current_session() -> str:
    """Today's context session."""
    # Resources don't have ctx in FastMCP - use module-level access
    # This is a limitation; for now return a placeholder
    return json.dumps({"info": "Use the session() tool for session data"})


# ========== ENTRY POINT ==========

def main():
    """Main entry point for MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
