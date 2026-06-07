"""
Command-Line Argument Parser
Defines all CLI commands and their arguments.

Architecture: CLI Layer (no business logic, only argument parsing)
"""

import argparse
from src.version import __version__


def create_parser() -> argparse.ArgumentParser:
    """
    Create argument parser with all 22 commands.

    Returns:
        Configured ArgumentParser

    Commands:
    - save, index, session, stats, tool-stats
    - search, smart-search, show, projects, vacuum, cleanup
    - snippet-add, snippet-search, snippet-show, snippet-list, snippet-delete
    - delete, project-delete, related
    - git-init, git-info, commit-info
    - ai-instruction, ai-instruction-update, ai-prompt
    - todo, test, infra
    """
    parser = argparse.ArgumentParser(
        description='ContextWolf - Local Knowledge System for Claude Code',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s save "Implemented JWT authentication"
  %(prog)s search "database migration"
  %(prog)s ai-prompt --quick
  %(prog)s todo add "Fix auth bug" --priority high
        """
    )

    # Add --version flag (-V for uppercase to avoid conflict with --verbose)
    parser.add_argument(
        '--version', '-V',
        action='version',
        version=f'%(prog)s {__version__}'
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    _add_save_command(subparsers)
    _add_index_command(subparsers)
    _add_session_command(subparsers)
    _add_stats_command(subparsers)
    _add_tool_stats_command(subparsers)
    _add_search_command(subparsers)
    _add_smart_search_command(subparsers)
    _add_show_command(subparsers)
    _add_projects_command(subparsers)
    _add_vacuum_command(subparsers)
    _add_cleanup_command(subparsers)
    _add_snippet_commands(subparsers)
    _add_delete_commands(subparsers)
    _add_related_command(subparsers)
    _add_git_commands(subparsers)
    _add_ai_commands(subparsers)
    _add_todo_commands(subparsers)
    _add_test_commands(subparsers)
    _add_infra_commands(subparsers)
    _add_now_commands(subparsers)
    _add_setup_commands(subparsers)

    return parser


def _add_save_command(subparsers):
    """Save action/decision"""
    save_parser = subparsers.add_parser('save', help='save action/decision')
    save_parser.add_argument('content', help='what was done/decided')
    save_parser.add_argument('--type', '-t', help='Type: code, decision, fix, command')
    save_parser.add_argument('--project', '-p', help='Project name')
    save_parser.add_argument('--metadata', '-m', help='JSON metadata (for git commits etc)')



def _add_index_command(subparsers):
    """Index MD files"""
    index_parser = subparsers.add_parser('index', help='index MD files')
    index_parser.add_argument('directory', nargs='?', default='.', help='Directory to index')


def _add_session_command(subparsers):
    """Show session"""
    session_parser = subparsers.add_parser('session', help='show session')
    session_parser.add_argument('--id', help='Session ID (default: current hour)')
    session_parser.add_argument('--verbose', '-v', action='store_true', help='verbose output')


def _add_stats_command(subparsers):
    """Show statistics"""
    subparsers.add_parser('stats', help='show statistics')


def _add_tool_stats_command(subparsers):
    """Show MCP tool usage statistics"""
    tool_stats_parser = subparsers.add_parser('tool-stats', help='show MCP tool usage statistics')
    tool_stats_parser.add_argument('--days', '-d', type=int, default=30, help='number of days to look back (default: 30)')
    tool_stats_parser.add_argument('--export', '-e', choices=['json', 'csv'], help='export format (json or csv)')


def _add_search_command(subparsers):
    """Search with FTS5"""
    search_parser = subparsers.add_parser('search', help='search with FTS5')
    search_parser.add_argument('query', help='search term')
    search_parser.add_argument('--type', '-t', help='filter by type')
    search_parser.add_argument('--limit', '-l', type=int, default=20, help='max results')
    search_parser.add_argument('--days', '-d', type=int, help='entries from the last X days only')
    search_parser.add_argument('--date-from', help='start date (YYYY-MM-DD) for time-travel search')
    search_parser.add_argument('--date-to', help='end date (YYYY-MM-DD) for time-travel search')
    search_parser.add_argument('--date', help='single date (YYYY-MM-DD)')
    search_parser.add_argument('--project', '-p', help='search in this project only')
    search_parser.add_argument('--all', '-a', action='store_true', help='search across all projects')


def _add_smart_search_command(subparsers):
    """Universal search across all content types"""
    smart_search = subparsers.add_parser('smart-search', help='Universal Search (instructions + snippets + actions)')
    smart_search.add_argument('query', help='search term')
    smart_search.add_argument('--limit', '-l', type=int, default=20, help='Max total results')
    smart_search.add_argument('--per-type', type=int, default=5, help='Max results per type')
    smart_search.add_argument('--types', nargs='+', choices=['instructions', 'snippets', 'actions'],
                            help='Filter content types (default: all)')


def _add_show_command(subparsers):
    """Show single entry details"""
    show_parser = subparsers.add_parser('show', help='show single entry details')
    show_parser.add_argument('entry_id', type=int, help='Entry ID')


def _add_projects_command(subparsers):
    """List projects"""
    subparsers.add_parser('projects', help='list all projects')


def _add_vacuum_command(subparsers):
    """Optimize database"""
    subparsers.add_parser('vacuum', help='optimize database')


def _add_cleanup_command(subparsers):
    """Cleanup indexed entries"""
    cleanup_parser = subparsers.add_parser('cleanup', help='Cleanup indexed entries')
    cleanup_parser.add_argument('--orphaned', action='store_true', help='Remove entries whose files no longer exist')
    cleanup_parser.add_argument('--legacy', action='store_true', help='List entries without file tracking')
    cleanup_parser.add_argument('--stats', action='store_true', help='Show file tracking statistics')
    cleanup_parser.add_argument('--force', action='store_true', help='Skip confirmation')
    cleanup_parser.add_argument('--sessions', action='store_true', help='List sessions shared across multiple projects')
    cleanup_parser.add_argument('--normalize-sessions', action='store_true', help='Normalize cross-project sessions to project-specific IDs')


def _add_snippet_commands(subparsers):
    """Snippet management commands"""
    snippet_add = subparsers.add_parser('snippet-add', help='add code snippet/template')
    snippet_add.add_argument('file_path', help='path to file')
    snippet_add.add_argument('--name', '-n', help='name for the snippet')
    snippet_add.add_argument('--desc', '-d', help='description')
    snippet_add.add_argument('--tags', '-t', nargs='+', help='tags')
    snippet_add.add_argument('--store', '-s', action='store_true', help='store full content')

    snippet_search = subparsers.add_parser('snippet-search', help='search snippets')
    snippet_search.add_argument('query', nargs='?', help='search term')
    snippet_search.add_argument('--type', '-t', help='Filter by file type')
    snippet_search.add_argument('--tags', nargs='+', help='Filter by tags')
    snippet_search.add_argument('--limit', '-l', type=int, default=20, help='Max results')

    snippet_show = subparsers.add_parser('snippet-show', help='show snippet details')
    snippet_show.add_argument('name', help='snippet name')
    snippet_show.add_argument('--cat', '-c', action='store_true', help='show full content')

    subparsers.add_parser('snippet-list', help='list all snippets')

    snippet_delete = subparsers.add_parser('snippet-delete', help='delete snippet')
    snippet_delete.add_argument('name', help='snippet name')
    snippet_delete.add_argument('--force', '-f', action='store_true', help='delete without confirmation')


def _add_delete_commands(subparsers):
    """Delete commands"""
    delete_parser = subparsers.add_parser('delete', help='delete an entry')
    delete_parser.add_argument('id', type=int, help='entry ID')
    delete_parser.add_argument('--force', '-f', action='store_true', help='delete without confirmation')

    project_delete = subparsers.add_parser('project-delete', help='delete an entire project')
    project_delete.add_argument('name', help='project name')
    project_delete.add_argument('--force', '-f', action='store_true', help='delete without confirmation')


def _add_related_command(subparsers):
    """Related entries"""
    related_parser = subparsers.add_parser('related', help='show related entries')
    related_parser.add_argument('id', type=int, help='entry ID')
    related_parser.add_argument('--limit', '-l', type=int, default=10, help='max count')


def _add_git_commands(subparsers):
    """Git integration commands"""
    git_init = subparsers.add_parser('git-init', help='install git hook')
    git_init.add_argument('--force', action='store_true', help='overwrite existing hook')
    git_init.add_argument('--global', dest='global_template', action='store_true', help='global for all repos')

    subparsers.add_parser('git-info', help='show git repository information')

    commit_info = subparsers.add_parser('commit-info', help='show details of a commit')
    commit_info.add_argument('id', nargs='?', type=int, help='entry ID of the commit')
    commit_info.add_argument('--hash', help='commit hash')
    commit_info.add_argument('--last', '-l', type=int, help='show last N commits')


def _add_ai_commands(subparsers):
    """AI instruction commands"""
    ai_prompt = subparsers.add_parser('ai-prompt', help='generate AI session prompt')
    ai_prompt.add_argument('--quick', '-q', action='store_true', help='short version')
    ai_prompt.add_argument('--verbose', '-v', action='store_true', help='verbose output')
    ai_prompt.add_argument('--smart', action='store_true', help='smart mode: session-aware filtering (8-55%% token reduction)')
    ai_prompt.add_argument('--hours', type=int, default=24, help='hours to look back for smart mode (default: 24)')
    ai_prompt.add_argument('--project', '-p', help='project')

    ai_instruction = subparsers.add_parser('ai-instruction', help='manage AI instructions')
    ai_instruction.add_argument('instruction', nargs='?', help='the AI instruction')
    ai_instruction.add_argument('--scope', '-s', choices=['global', 'project', 'session'], default='project')
    ai_instruction.add_argument('--priority', '-pr', choices=['must', 'should', 'nice'], default='should')
    ai_instruction.add_argument('--category', '-c',
                                choices=['security', 'style', 'performance', 'architecture', 'testing', 'general'])
    ai_instruction.add_argument('--rationale', '-r', help='rationale')
    ai_instruction.add_argument('--example-good', help='correct example')
    ai_instruction.add_argument('--example-bad', help='incorrect example')
    ai_instruction.add_argument('--list', '-l', action='store_true', help='list all')
    ai_instruction.add_argument('--show', type=int, help='show full instruction')
    ai_instruction.add_argument('--search', help='search in instructions (full text + metadata)')
    ai_instruction.add_argument('--search-category', help='filter by category (infrastructure, security, etc.)')
    ai_instruction.add_argument('--search-priority', choices=['must', 'should', 'nice'], help='filter by priority')
    ai_instruction.add_argument('--search-scope', choices=['global', 'project', 'session'], help='filter by scope')
    ai_instruction.add_argument('--toggle', type=int, help='enable/disable by ID')
    ai_instruction.add_argument('--template', '-t', help='load template')
    ai_instruction.add_argument('--project', '-p', help='project')
    ai_instruction.add_argument('--delete', type=int, help='delete instruction by ID')
    ai_instruction.add_argument('--force', '-f', action='store_true', help='skip confirmation prompt when deleting')

    ai_update = subparsers.add_parser('ai-instruction-update', help='update AI instruction')
    ai_update.add_argument('id', type=int, help='instruction ID')
    ai_update.add_argument('--scope', '-s', choices=['global', 'project', 'session'])
    ai_update.add_argument('--priority', '-pr', choices=['must', 'should', 'nice'])
    ai_update.add_argument('--category', '-c',
                          choices=['security', 'style', 'performance', 'architecture', 'testing', 'general'])
    ai_update.add_argument('--toggle', '-t', action='store_true', help='Toggle active/inactive')
    ai_update.add_argument('--instruction', help='new instruction text')
    ai_update.add_argument('--rationale', '-r', help='updated rationale')
    ai_update.add_argument('--clear-rationale', action='store_true', help='remove existing rationale')
    ai_update.add_argument('--example-good', help='update good example')
    ai_update.add_argument('--example-bad', help='update bad example')
    ai_update.add_argument('--clear-examples', action='store_true', help='remove all examples')


def _add_todo_commands(subparsers):
    """TODO management commands"""
    # Main todo command with subcommands
    todo_parser = subparsers.add_parser('todo', help='TODO Management System')
    todo_subparsers = todo_parser.add_subparsers(dest='todo_command', help='TODO commands')

    # todo add
    todo_add = todo_subparsers.add_parser('add', help='add new TODO')
    todo_add.add_argument('summary', help='TODO description')
    todo_add.add_argument('--content', '-c', help='detailed description')
    todo_add.add_argument('--priority', '-p', choices=['high', 'normal', 'low'], default='normal',
                         help='priority (default: normal)')
    todo_add.add_argument('--category', '-cat', help='category (bug, feature, docs, etc.)')
    todo_add.add_argument('--due', '-d', help='due date (YYYY-MM-DD)')
    todo_add.add_argument('--tags', '-t', nargs='+', help='tags')
    todo_add.add_argument('--depends', nargs='+', type=int, help='depends on TODO IDs')
    todo_add.add_argument('--assign', '-a', help='assigned to')
    todo_add.add_argument('--project', help='project name')

    # todo list
    todo_list = todo_subparsers.add_parser('list', help='list TODOs')
    todo_list.add_argument('--status', '-s', choices=['open', 'in_progress', 'done', 'cancelled'],
                          help='filter by status')
    todo_list.add_argument('--priority', '-p', choices=['high', 'normal', 'low'],
                          help='filter by priority')
    todo_list.add_argument('--category', '-cat', help='filter by category')
    todo_list.add_argument('--assigned', '-a', help='filter by assignee')
    todo_list.add_argument('--all', action='store_true', help='show completed TODOs as well')
    todo_list.add_argument('--all-projects', action='store_true', help='show TODOs across all projects')
    todo_list.add_argument('--project', help='filter by project')
    todo_list.add_argument('--limit', '-l', type=int, default=50, help='max count (default: 50)')

    # todo done (bulk support)
    todo_done = todo_subparsers.add_parser('done', help='mark TODO(s) as done')
    todo_done.add_argument('ids', nargs='+', type=int, help='TODO ID(s)')
    todo_done.add_argument('--force', '-f', action='store_true',
                          help='ignore dependencies')

    # todo start (mark as in_progress)
    todo_start = todo_subparsers.add_parser('start', help='mark TODO as in progress')
    todo_start.add_argument('id', type=int, help='TODO ID')

    # todo reopen (bulk support)
    todo_reopen = todo_subparsers.add_parser('reopen', help='reopen TODO(s)')
    todo_reopen.add_argument('ids', nargs='+', type=int, help='TODO ID(s)')

    # todo cancel
    todo_cancel = todo_subparsers.add_parser('cancel', help='cancel TODO')
    todo_cancel.add_argument('ids', nargs='+', type=int, help='TODO ID(s)')

    # todo delete (bulk support)
    todo_delete = todo_subparsers.add_parser('delete', help='permanently delete TODO(s)')
    todo_delete.add_argument('ids', nargs='+', type=int, help='TODO ID(s)')
    todo_delete.add_argument('--force', '-f', action='store_true',
                            help='delete without confirmation')

    # todo show (details)
    todo_show = todo_subparsers.add_parser('show', help='show TODO details')
    todo_show.add_argument('id', type=int, help='TODO ID')

    # todo stats
    todo_stats = todo_subparsers.add_parser('stats', help='TODO statistics')
    todo_stats.add_argument('--project', help='filter by project')

    # todo stale
    todo_stale = todo_subparsers.add_parser('stale', help='show stale, unprocessed TODOs')
    todo_stale.add_argument('--days', '-d', type=int, default=7,
                           help='days without update (default: 7)')

    # todo suggest
    todo_suggest = todo_subparsers.add_parser('suggest', help='AI-based TODO suggestions')
    todo_suggest.add_argument('--project', help='project context')
    todo_suggest.add_argument('--limit', '-l', type=int, default=5,
                             help='number of suggestions (default: 5)')


def _add_test_commands(subparsers):
    """Test management commands"""
    test_parser = subparsers.add_parser('test', help='Test Management System')
    test_subparsers = test_parser.add_subparsers(dest='test_command', help='Test commands')

    # test suite-add
    suite_add = test_subparsers.add_parser('suite-add', help='create new test suite')
    suite_add.add_argument('name', help='suite name')
    suite_add.add_argument('--desc', help='description')
    suite_add.add_argument('--project', '-p', help='project name')
    suite_add.add_argument('--tags', nargs='*', help='Tags (space-separated)')

    # test suite-list
    suite_list = test_subparsers.add_parser('suite-list', help='list test suites')
    suite_list.add_argument('--project', '-p', help='filter by project')
    suite_list.add_argument('--all', action='store_true', help='include inactive suites')

    # test suite-update
    suite_update = test_subparsers.add_parser('suite-update', help='update test suite')
    suite_update.add_argument('suite_id', type=int, help='test suite ID')
    suite_update.add_argument('--name', help='new name')
    suite_update.add_argument('--desc', help='new description')
    suite_update.add_argument('--tags', nargs='*', help='new tags (space-separated)')

    # test case-add
    case_add = test_subparsers.add_parser('case-add', help='add test case')
    case_add.add_argument('suite_id', type=int, help='test suite ID')
    case_add.add_argument('name', help='test case name')
    case_add.add_argument('command', help='command to execute')
    case_add.add_argument('--desc', help='description')
    case_add.add_argument('--cwd', help='Working directory')
    case_add.add_argument('--timeout', type=int, default=300, help='Timeout in seconds (default: 300)')
    case_add.add_argument('--exit-code', type=int, default=0, help='Expected exit code (default: 0)')
    case_add.add_argument('--priority', choices=['critical', 'high', 'normal', 'low'],
                         default='normal', help='Priority level')
    case_add.add_argument('--tags', nargs='*', help='Tags (space-separated)')

    # test case-list
    case_list = test_subparsers.add_parser('case-list', help='list test cases')
    case_list.add_argument('--suite', type=int, help='filter by suite ID')
    case_list.add_argument('--priority', help='filter by priority')
    case_list.add_argument('--all', action='store_true', help='include inactive cases')

    # test case-update
    case_update = test_subparsers.add_parser('case-update', help='update test case')
    case_update.add_argument('test_case_id', type=int, help='test case ID')
    case_update.add_argument('--name', help='new name')
    case_update.add_argument('--command', help='new command')
    case_update.add_argument('--desc', help='new description')
    case_update.add_argument('--cwd', help='new working directory')
    case_update.add_argument('--timeout', type=int, help='new timeout in seconds')
    case_update.add_argument('--exit-code', type=int, help='new expected exit code')
    case_update.add_argument('--priority', choices=['critical', 'high', 'normal', 'low'],
                         help='new priority')
    case_update.add_argument('--tags', nargs='*', help='new tags (space-separated)')

    # test exec
    test_exec = test_subparsers.add_parser('exec', help='execute test case')
    test_exec.add_argument('test_case_id', type=int, help='test case ID')
    test_exec.add_argument('--save-output', action='store_true', default=True,
                          help='store full output (default: True)')
    test_exec.add_argument('--env', nargs='*', help='Environment variables (KEY=VALUE)')

    # test run-suite
    run_suite = test_subparsers.add_parser('run-suite', help='run all tests in a suite')
    run_suite.add_argument('suite_id', type=int, help='test suite ID')
    run_suite.add_argument('--priority', help='only tests with this priority')
    run_suite.add_argument('--stop-on-fail', action='store_true',
                          help='stop on first failure')

    # test history
    test_history = test_subparsers.add_parser('history', help='show execution history')
    test_history.add_argument('test_case_id', type=int, help='test case ID')
    test_history.add_argument('--limit', '-l', type=int, default=10,
                             help='number of entries (default: 10)')

    # test stats
    test_stats = test_subparsers.add_parser('stats', help='test statistics')
    test_stats.add_argument('--suite', type=int, help='suite ID')
    test_stats.add_argument('--case', type=int, help='test case ID')
    test_stats.add_argument('--project', '-p', help='project name')
    test_stats.add_argument('--days', type=int, default=30, help='time range in days (default: 30)')

    # test failures
    test_failures = test_subparsers.add_parser('failures', help='show recent failures')
    test_failures.add_argument('--project', '-p', help='filter by project')
    test_failures.add_argument('--limit', '-l', type=int, default=10,
                              help='number of entries (default: 10)')

    # test flaky
    test_flaky = test_subparsers.add_parser('flaky', help='identify flaky tests')
    test_flaky.add_argument('--project', '-p', help='filter by project')
    test_flaky.add_argument('--min-runs', type=int, default=5,
                           help='minimum number of runs (default: 5)')

    # test coverage
    test_coverage = test_subparsers.add_parser('coverage', help='show test coverage')
    test_coverage.add_argument('project', help='project name')


def _add_infra_commands(subparsers):
    """Infrastructure management commands"""
    infra_parser = subparsers.add_parser('infra', help='Infrastructure Management (SSH Hosts & Services)')
    infra_subparsers = infra_parser.add_subparsers(dest='infra_command', help='infra subcommands')

    # ========== HOST COMMANDS ==========

    # infra add-host
    add_host = infra_subparsers.add_parser('add-host', help='add SSH host')
    add_host.add_argument('hostname', help='SSH Hostname (e.g., prod-server-01)')
    add_host.add_argument('--ip', help='IP Address')
    add_host.add_argument('--port', type=int, default=22, help='SSH Port (default: 22)')
    add_host.add_argument('--user', '-u', help='SSH User')
    add_host.add_argument('--identity-file', '-i', help='Path to SSH key')
    add_host.add_argument('--location', '-l', choices=['local', 'extern'],
                         help='Location: local or extern')
    add_host.add_argument('--provider', help='Provider (e.g., Netcup, AWS)')
    add_host.add_argument('--server-type', help='Server type (e.g., VPS, Shared, Raspberry)')
    add_host.add_argument('--scope', choices=['global', 'project'], default='global',
                         help='Scope: global or project (default: global)')
    add_host.add_argument('--project', '-p', help='Project name (for project scope)')
    add_host.add_argument('--tags', '-t', nargs='+', help='Tags')
    add_host.add_argument('--comment', '-c', help='Comment')

    # infra list-hosts
    list_hosts = infra_subparsers.add_parser('list-hosts', help='list SSH hosts')
    list_hosts.add_argument('--scope', choices=['global', 'project'], help='Filter by scope')
    list_hosts.add_argument('--location', '-l', choices=['local', 'extern'],
                           help='Filter by location')
    list_hosts.add_argument('--project', '-p', help='Filter by project')
    list_hosts.add_argument('--tags', '-t', nargs='+', help='Filter by tags')
    list_hosts.add_argument('--minimal', '-m', action='store_true',
                           help='Minimal output (hostname, location, tags only)')

    # infra show-host
    show_host = infra_subparsers.add_parser('show-host', help='show host details')
    show_host.add_argument('hostname', help='Hostname')

    # infra edit-host
    edit_host = infra_subparsers.add_parser('edit-host', help='edit host')
    edit_host.add_argument('hostname', help='Hostname to edit')
    edit_host.add_argument('--ip', help='New IP address')
    edit_host.add_argument('--port', type=int, help='New SSH port')
    edit_host.add_argument('--user', '-u', help='New SSH user')
    edit_host.add_argument('--identity-file', '-i', help='New SSH key path')
    edit_host.add_argument('--location', '-l', choices=['local', 'extern'], help='New location')
    edit_host.add_argument('--provider', help='New provider')
    edit_host.add_argument('--server-type', help='New server type')
    edit_host.add_argument('--tags', '-t', nargs='+', help='New tags (replaces existing)')
    edit_host.add_argument('--comment', '-c', help='New comment')

    # infra delete-host
    delete_host = infra_subparsers.add_parser('delete-host', help='delete host')
    delete_host.add_argument('hostname', help='Hostname to delete')
    delete_host.add_argument('--force', '-f', action='store_true',
                            help='Force deletion even if services exist')

    # ========== SERVICE COMMANDS ==========

    # infra add-service
    add_service = infra_subparsers.add_parser('add-service', help='add service')
    add_service.add_argument('hostname', help='Host where service runs')
    add_service.add_argument('service_name', help='Service name')
    add_service.add_argument('--env', '-e', choices=['prod', 'staging', 'dev', 'test'],
                            help='Environment')
    add_service.add_argument('--path', help='Application path on host')
    add_service.add_argument('--type', help='Service type (docker, systemd, pm2, etc.)')
    add_service.add_argument('--deploy-method', help='Deployment method')
    add_service.add_argument('--health-url', help='Health check URL')
    add_service.add_argument('--scope', choices=['global', 'project'], default='project',
                            help='Scope (default: project)')
    add_service.add_argument('--project', '-p', help='Project name')
    add_service.add_argument('--tags', '-t', nargs='+', help='Tags')
    add_service.add_argument('--comment', '-c', help='Comment')

    # infra list-services
    list_services = infra_subparsers.add_parser('list-services', help='list services')
    list_services.add_argument('--host', help='Filter by hostname')
    list_services.add_argument('--env', '-e', choices=['prod', 'staging', 'dev', 'test'],
                              help='Filter by environment')
    list_services.add_argument('--scope', choices=['global', 'project'], help='Filter by scope')
    list_services.add_argument('--project', '-p', help='Filter by project')

    # infra edit-service
    edit_service = infra_subparsers.add_parser('edit-service', help='edit service')
    edit_service.add_argument('hostname', help='Hostname where service runs')
    edit_service.add_argument('service_name', help='Service name to edit')
    edit_service.add_argument('--env', '-e', choices=['prod', 'staging', 'dev', 'test'],
                             help='New environment')
    edit_service.add_argument('--path', help='New application path')
    edit_service.add_argument('--type', help='New service type')
    edit_service.add_argument('--deploy-method', help='New deployment method (e.g., ssh, local)')
    edit_service.add_argument('--health-url', help='New health check URL')
    edit_service.add_argument('--tags', '-t', nargs='+', help='New tags (replaces existing)')
    edit_service.add_argument('--comment', '-c', help='New comment')

    # infra delete-service
    delete_service = infra_subparsers.add_parser('delete-service', help='delete service')
    delete_service.add_argument('hostname', help='Hostname')
    delete_service.add_argument('service_name', help='Service name to delete')


def _add_now_commands(subparsers):
    """'Now' sprint backlog commands (cross-project shortlist)."""
    now_parser = subparsers.add_parser(
        'now',
        help='Now: cross-project sprint backlog (today / week / later)'
    )
    now_sub = now_parser.add_subparsers(dest='now_command', help='now subcommands')

    # now add
    n_add = now_sub.add_parser('add', help='add an item to the Now list')
    n_add.add_argument('title', help='short, action-oriented title (max 200 chars)')
    n_add.add_argument('--bucket', '-b', choices=['today', 'week', 'later'],
                       default='today', help="target bucket (default: today)")
    n_add.add_argument('--project', '-p', help='project name (optional)')
    n_add.add_argument('--link-type', choices=[
        'todo', 'action', 'note', 'snippet', 'ai_instruction', 'host', 'service'
    ], help='reference an existing CM entity by type')
    n_add.add_argument('--link-id', type=int, help='ID of the linked entity (required with --link-type)')

    # now list
    n_list = now_sub.add_parser('list', help='list Now items')
    n_list.add_argument('--bucket', '-b', choices=['today', 'week', 'later', 'done'],
                        help='filter by bucket')
    n_list.add_argument('--project', '-p', help='filter by project')
    n_list.add_argument('--all', action='store_true',
                        help="include 'done' bucket")
    n_list.add_argument('--json', action='store_true',
                        help='emit raw JSON (the UI contract)')

    # now show
    n_show = now_sub.add_parser('show', help='show a Now item')
    n_show.add_argument('id', type=int, help='Now item ID')

    # now move
    n_move = now_sub.add_parser('move', help='move a Now item to another bucket')
    n_move.add_argument('id', type=int, help='Now item ID')
    n_move.add_argument('bucket', choices=['today', 'week', 'later'],
                        help='target bucket')

    # now done
    n_done = now_sub.add_parser('done', help='mark a Now item as done')
    n_done.add_argument('id', type=int, help='Now item ID')

    # now remove
    n_remove = now_sub.add_parser('remove', help='delete a Now item')
    n_remove.add_argument('id', type=int, help='Now item ID')

    # now reorder
    n_reorder = now_sub.add_parser('reorder', help='reorder items in a bucket')
    n_reorder.add_argument('bucket', choices=['today', 'week', 'later', 'done'],
                           help='bucket to reorder')
    n_reorder.add_argument('ids', nargs='+', type=int,
                           help='item IDs in the new order (must match the bucket exactly)')

    # now settings
    n_settings = now_sub.add_parser('settings', help='show or update WIP limits')
    n_settings.add_argument('--today', type=int, help='new limit for today (1-100)')
    n_settings.add_argument('--week', type=int, help='new limit for week (1-100)')
    n_settings.add_argument('--later', type=int, help='new limit for later (1-100)')


def _add_setup_commands(subparsers):
    """Setup and diagnostics commands (run without DB connection)"""
    subparsers.add_parser('init', help='Interactive setup wizard (configure DB, start Docker)')
    subparsers.add_parser('doctor', help='Check prerequisites and system health')
    subparsers.add_parser('setup-mcp', help='Configure MCP server in ~/.claude.json')

    pinned_parser = subparsers.add_parser('pinned', help='list pinned items curated in GUI (read-only)')
    pinned_parser.add_argument('--project', '-p', help='filter by project (global + project items)')
    pinned_parser.add_argument('--json', action='store_true', help='JSON output instead of Markdown')
