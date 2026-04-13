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
    - save, check, index, session, stats
    - search, projects, vacuum, tokens
    - snippet-add, snippet-search, snippet-show, snippet-list, snippet-delete
    - delete, project-delete, related
    - git-init, git-info, commit-info
    - ai-instruction, ai-instruction-update, ai-prompt
    """
    parser = argparse.ArgumentParser(
        description='ContextWolf - Local Knowledge System for Claude Code',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s save "Implemented JWT authentication"
  %(prog)s check "Will implement MongoDB"
  %(prog)s search "database migration"
  %(prog)s ai --quick
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
    _add_tokens_command(subparsers)
    _add_snippet_commands(subparsers)
    _add_delete_commands(subparsers)
    _add_related_command(subparsers)
    _add_git_commands(subparsers)
    _add_ai_commands(subparsers)
    _add_todo_commands(subparsers)
    _add_test_commands(subparsers)
    _add_infra_commands(subparsers)
    _add_setup_commands(subparsers)

    return parser


def _add_save_command(subparsers):
    """Save action/decision"""
    save_parser = subparsers.add_parser('save', help='Speichere Aktion/Entscheidung')
    save_parser.add_argument('content', help='Was wurde gemacht/entschieden')
    save_parser.add_argument('--type', '-t', help='Type: code, decision, fix, command')
    save_parser.add_argument('--project', '-p', help='Project name')
    save_parser.add_argument('--metadata', '-m', help='JSON metadata (for git commits etc)')



def _add_index_command(subparsers):
    """Index MD files"""
    index_parser = subparsers.add_parser('index', help='Indexiere MD Files')
    index_parser.add_argument('directory', nargs='?', default='.', help='Directory to index')


def _add_session_command(subparsers):
    """Show session"""
    session_parser = subparsers.add_parser('session', help='Zeige Session')
    session_parser.add_argument('--id', help='Session ID (default: current hour)')
    session_parser.add_argument('--verbose', '-v', action='store_true', help='Zeige detaillierte Ausgabe')


def _add_stats_command(subparsers):
    """Show statistics"""
    subparsers.add_parser('stats', help='Zeige Statistiken')


def _add_tool_stats_command(subparsers):
    """Show MCP tool usage statistics"""
    tool_stats_parser = subparsers.add_parser('tool-stats', help='Zeige MCP Tool Usage Statistiken')
    tool_stats_parser.add_argument('--days', '-d', type=int, default=30, help='Anzahl der Tage zurück (default: 30)')
    tool_stats_parser.add_argument('--export', '-e', choices=['json', 'csv'], help='Export format (json oder csv)')


def _add_search_command(subparsers):
    """Search with FTS5"""
    search_parser = subparsers.add_parser('search', help='Suche mit FTS5')
    search_parser.add_argument('query', help='Suchbegriff')
    search_parser.add_argument('--type', '-t', help='Filter by type')
    search_parser.add_argument('--limit', '-l', type=int, default=20, help='Max results')
    search_parser.add_argument('--days', '-d', type=int, help='Nur Einträge der letzten X Tage')
    search_parser.add_argument('--date-from', help='Startdatum (YYYY-MM-DD) für Time-Travel Search')
    search_parser.add_argument('--date-to', help='Enddatum (YYYY-MM-DD) für Time-Travel Search')
    search_parser.add_argument('--date', help='Einzelnes Datum (YYYY-MM-DD)')
    search_parser.add_argument('--project', '-p', help='Nur in diesem Projekt')
    search_parser.add_argument('--all', '-a', action='store_true', help='In ALLEN Projekten suchen')


def _add_smart_search_command(subparsers):
    """Universal search across all content types"""
    smart_search = subparsers.add_parser('smart-search', help='Universal Search (instructions + snippets + actions)')
    smart_search.add_argument('query', help='Suchbegriff')
    smart_search.add_argument('--limit', '-l', type=int, default=20, help='Max total results')
    smart_search.add_argument('--per-type', type=int, default=5, help='Max results per type')
    smart_search.add_argument('--types', nargs='+', choices=['instructions', 'snippets', 'actions'],
                            help='Filter content types (default: all)')


def _add_show_command(subparsers):
    """Show single entry details"""
    show_parser = subparsers.add_parser('show', help='Zeige einzelnen Eintrag')
    show_parser.add_argument('entry_id', type=int, help='Entry ID')


def _add_projects_command(subparsers):
    """List projects"""
    subparsers.add_parser('projects', help='Liste alle Projekte')


def _add_vacuum_command(subparsers):
    """Optimize database"""
    subparsers.add_parser('vacuum', help='Optimiere Datenbank')


def _add_cleanup_command(subparsers):
    """Cleanup indexed entries"""
    cleanup_parser = subparsers.add_parser('cleanup', help='Cleanup indexed entries')
    cleanup_parser.add_argument('--orphaned', action='store_true', help='Remove entries whose files no longer exist')
    cleanup_parser.add_argument('--legacy', action='store_true', help='List entries without file tracking')
    cleanup_parser.add_argument('--stats', action='store_true', help='Show file tracking statistics')
    cleanup_parser.add_argument('--force', action='store_true', help='Skip confirmation')
    cleanup_parser.add_argument('--sessions', action='store_true', help='List sessions shared across multiple projects')
    cleanup_parser.add_argument('--normalize-sessions', action='store_true', help='Normalize cross-project sessions to project-specific IDs')


def _add_tokens_command(subparsers):
    """Show token usage"""
    subparsers.add_parser('tokens', help='Zeige Token-Verbrauch')


def _add_snippet_commands(subparsers):
    """Snippet management commands"""
    snippet_add = subparsers.add_parser('snippet-add', help='Füge Code-Snippet/Template hinzu')
    snippet_add.add_argument('file_path', help='Pfad zum File')
    snippet_add.add_argument('--name', '-n', help='Name für das Snippet')
    snippet_add.add_argument('--desc', '-d', help='Beschreibung')
    snippet_add.add_argument('--tags', '-t', nargs='+', help='Tags')
    snippet_add.add_argument('--store', '-s', action='store_true', help='Speichere vollständigen Inhalt')

    snippet_search = subparsers.add_parser('snippet-search', help='Suche Snippets')
    snippet_search.add_argument('query', nargs='?', help='Suchbegriff')
    snippet_search.add_argument('--type', '-t', help='Filter by file type')
    snippet_search.add_argument('--tags', nargs='+', help='Filter by tags')
    snippet_search.add_argument('--limit', '-l', type=int, default=20, help='Max results')

    snippet_show = subparsers.add_parser('snippet-show', help='Zeige Snippet Details')
    snippet_show.add_argument('name', help='Snippet Name')
    snippet_show.add_argument('--cat', '-c', action='store_true', help='Zeige vollständigen Inhalt')

    subparsers.add_parser('snippet-list', help='Liste alle Snippets')

    snippet_delete = subparsers.add_parser('snippet-delete', help='Lösche Snippet')
    snippet_delete.add_argument('name', help='Snippet Name')
    snippet_delete.add_argument('--force', '-f', action='store_true', help='Ohne Bestätigung löschen')


def _add_delete_commands(subparsers):
    """Delete commands"""
    delete_parser = subparsers.add_parser('delete', help='Lösche einen Eintrag')
    delete_parser.add_argument('id', type=int, help='ID des Eintrags')
    delete_parser.add_argument('--force', '-f', action='store_true', help='Ohne Bestätigung löschen')

    project_delete = subparsers.add_parser('project-delete', help='Lösche ein komplettes Projekt')
    project_delete.add_argument('name', help='Name des Projekts')
    project_delete.add_argument('--force', '-f', action='store_true', help='Ohne Bestätigung löschen')


def _add_related_command(subparsers):
    """Related entries"""
    related_parser = subparsers.add_parser('related', help='Zeige verwandte Einträge')
    related_parser.add_argument('id', type=int, help='ID des Eintrags')
    related_parser.add_argument('--limit', '-l', type=int, default=10, help='Max. Anzahl')


def _add_git_commands(subparsers):
    """Git integration commands"""
    git_init = subparsers.add_parser('git-init', help='Installiere Git-Hook')
    git_init.add_argument('--force', action='store_true', help='Überschreibe existierenden Hook')
    git_init.add_argument('--global', dest='global_template', action='store_true', help='Global für alle Repos')

    subparsers.add_parser('git-info', help='Zeige Git-Repository Informationen')

    commit_info = subparsers.add_parser('commit-info', help='Zeige Details eines Commits')
    commit_info.add_argument('id', nargs='?', type=int, help='Entry ID des Commits')
    commit_info.add_argument('--hash', help='Commit Hash')
    commit_info.add_argument('--last', '-l', type=int, help='Zeige letzte N Commits')


def _add_ai_commands(subparsers):
    """AI instruction commands"""
    ai_prompt = subparsers.add_parser('ai-prompt', help='Generiere KI-Session Prompt')
    ai_prompt.add_argument('--quick', '-q', action='store_true', help='Kurze Version')
    ai_prompt.add_argument('--verbose', '-v', action='store_true', help='Ausführliche Version')
    ai_prompt.add_argument('--smart', action='store_true', help='Smart Mode: Session-aware filtering (8-55%% Token-Reduktion)')
    ai_prompt.add_argument('--hours', type=int, default=24, help='Stunden zurückblicken für Smart-Mode (default: 24)')
    ai_prompt.add_argument('--project', '-p', help='Projekt')

    ai_instruction = subparsers.add_parser('ai-instruction', help='Verwalte KI-Anweisungen')
    ai_instruction.add_argument('instruction', nargs='?', help='Die KI-Anweisung')
    ai_instruction.add_argument('--scope', '-s', choices=['global', 'project', 'session'], default='project')
    ai_instruction.add_argument('--priority', '-pr', choices=['must', 'should', 'nice'], default='should')
    ai_instruction.add_argument('--category', '-c',
                                choices=['security', 'style', 'performance', 'architecture', 'testing', 'general'])
    ai_instruction.add_argument('--rationale', '-r', help='Begründung')
    ai_instruction.add_argument('--example-good', help='Beispiel korrekt')
    ai_instruction.add_argument('--example-bad', help='Beispiel falsch')
    ai_instruction.add_argument('--list', '-l', action='store_true', help='Liste alle')
    ai_instruction.add_argument('--show', type=int, help='Zeige vollständige Instruction')
    ai_instruction.add_argument('--search', help='Suche in Anweisungen (Volltext + Metadata)')
    ai_instruction.add_argument('--search-category', help='Filter nach Category (infrastructure, security, etc.)')
    ai_instruction.add_argument('--search-priority', choices=['must', 'should', 'nice'], help='Filter nach Priority')
    ai_instruction.add_argument('--search-scope', choices=['global', 'project', 'session'], help='Filter nach Scope')
    ai_instruction.add_argument('--toggle', type=int, help='Aktiviere/Deaktiviere ID')
    ai_instruction.add_argument('--template', '-t', help='Lade Template')
    ai_instruction.add_argument('--project', '-p', help='Projekt')
    ai_instruction.add_argument('--delete', type=int, help='Lösche Anweisung nach ID')
    ai_instruction.add_argument('--force', '-f', action='store_true', help='Überspringt Sicherheitsabfrage beim Löschen')

    ai_update = subparsers.add_parser('ai-instruction-update', help='Update KI-Anweisung')
    ai_update.add_argument('id', type=int, help='ID der Anweisung')
    ai_update.add_argument('--scope', '-s', choices=['global', 'project', 'session'])
    ai_update.add_argument('--priority', '-pr', choices=['must', 'should', 'nice'])
    ai_update.add_argument('--category', '-c',
                          choices=['security', 'style', 'performance', 'architecture', 'testing', 'general'])
    ai_update.add_argument('--toggle', '-t', action='store_true', help='Toggle active/inactive')
    ai_update.add_argument('--instruction', help='Neuer Instruction-Text')
    ai_update.add_argument('--rationale', '-r', help='Aktualisierte Begründung')
    ai_update.add_argument('--clear-rationale', action='store_true', help='Entfernt vorhandene Begründung')
    ai_update.add_argument('--example-good', help='Aktualisiere Good Example')
    ai_update.add_argument('--example-bad', help='Aktualisiere Bad Example')
    ai_update.add_argument('--clear-examples', action='store_true', help='Entfernt alle Beispiele')


def _add_todo_commands(subparsers):
    """TODO management commands"""
    # Main todo command with subcommands
    todo_parser = subparsers.add_parser('todo', help='TODO Management System')
    todo_subparsers = todo_parser.add_subparsers(dest='todo_command', help='TODO commands')

    # todo add
    todo_add = todo_subparsers.add_parser('add', help='Füge neues TODO hinzu')
    todo_add.add_argument('summary', help='TODO Beschreibung')
    todo_add.add_argument('--content', '-c', help='Detaillierte Beschreibung')
    todo_add.add_argument('--priority', '-p', choices=['high', 'normal', 'low'], default='normal',
                         help='Priorität (default: normal)')
    todo_add.add_argument('--category', '-cat', help='Kategorie (bug, feature, docs, etc.)')
    todo_add.add_argument('--due', '-d', help='Fälligkeitsdatum (YYYY-MM-DD)')
    todo_add.add_argument('--tags', '-t', nargs='+', help='Tags')
    todo_add.add_argument('--depends', nargs='+', type=int, help='Abhängig von TODO IDs')
    todo_add.add_argument('--assign', '-a', help='Zugewiesen an')
    todo_add.add_argument('--project', help='Projekt Name')

    # todo list
    todo_list = todo_subparsers.add_parser('list', help='Liste TODOs')
    todo_list.add_argument('--status', '-s', choices=['open', 'in_progress', 'done', 'cancelled'],
                          help='Filter nach Status')
    todo_list.add_argument('--priority', '-p', choices=['high', 'normal', 'low'],
                          help='Filter nach Priorität')
    todo_list.add_argument('--category', '-cat', help='Filter nach Kategorie')
    todo_list.add_argument('--assigned', '-a', help='Filter nach Zugewiesenem')
    todo_list.add_argument('--all', action='store_true', help='Zeige auch erledigte TODOs')
    todo_list.add_argument('--all-projects', action='store_true', help='Zeige TODOs aus allen Projekten')
    todo_list.add_argument('--project', help='Filter nach Projekt')
    todo_list.add_argument('--limit', '-l', type=int, default=50, help='Max Anzahl (default: 50)')

    # todo done (bulk support)
    todo_done = todo_subparsers.add_parser('done', help='Markiere TODO(s) als erledigt')
    todo_done.add_argument('ids', nargs='+', type=int, help='TODO ID(s)')
    todo_done.add_argument('--force', '-f', action='store_true',
                          help='Ignoriere Abhängigkeiten')

    # todo start (mark as in_progress)
    todo_start = todo_subparsers.add_parser('start', help='Markiere TODO als in Bearbeitung')
    todo_start.add_argument('id', type=int, help='TODO ID')

    # todo reopen (bulk support)
    todo_reopen = todo_subparsers.add_parser('reopen', help='Öffne TODO(s) wieder')
    todo_reopen.add_argument('ids', nargs='+', type=int, help='TODO ID(s)')

    # todo cancel
    todo_cancel = todo_subparsers.add_parser('cancel', help='Breche TODO ab')
    todo_cancel.add_argument('ids', nargs='+', type=int, help='TODO ID(s)')

    # todo delete (bulk support)
    todo_delete = todo_subparsers.add_parser('delete', help='Lösche TODO(s) permanent')
    todo_delete.add_argument('ids', nargs='+', type=int, help='TODO ID(s)')
    todo_delete.add_argument('--force', '-f', action='store_true',
                            help='Ohne Nachfrage löschen')

    # todo show (details)
    todo_show = todo_subparsers.add_parser('show', help='Zeige TODO Details')
    todo_show.add_argument('id', type=int, help='TODO ID')

    # todo stats
    todo_stats = todo_subparsers.add_parser('stats', help='TODO Statistiken')
    todo_stats.add_argument('--project', help='Filter nach Projekt')

    # todo stale
    todo_stale = todo_subparsers.add_parser('stale', help='Zeige alte, unbearbeitete TODOs')
    todo_stale.add_argument('--days', '-d', type=int, default=7,
                           help='Tage ohne Update (default: 7)')

    # todo suggest
    todo_suggest = todo_subparsers.add_parser('suggest', help='KI-basierte TODO Vorschläge')
    todo_suggest.add_argument('--project', help='Projekt Kontext')
    todo_suggest.add_argument('--limit', '-l', type=int, default=5,
                             help='Anzahl Vorschläge (default: 5)')


def _add_test_commands(subparsers):
    """Test management commands"""
    test_parser = subparsers.add_parser('test', help='Test Management System')
    test_subparsers = test_parser.add_subparsers(dest='test_command', help='Test commands')

    # test suite-add
    suite_add = test_subparsers.add_parser('suite-add', help='Neue Test Suite erstellen')
    suite_add.add_argument('name', help='Suite Name')
    suite_add.add_argument('--desc', help='Beschreibung')
    suite_add.add_argument('--project', '-p', help='Projekt Name')
    suite_add.add_argument('--tags', nargs='*', help='Tags (space-separated)')

    # test suite-list
    suite_list = test_subparsers.add_parser('suite-list', help='Test Suites auflisten')
    suite_list.add_argument('--project', '-p', help='Filter nach Projekt')
    suite_list.add_argument('--all', action='store_true', help='Auch inaktive Suites')

    # test suite-update
    suite_update = test_subparsers.add_parser('suite-update', help='Test Suite aktualisieren')
    suite_update.add_argument('suite_id', type=int, help='Test Suite ID')
    suite_update.add_argument('--name', help='Neuer Name')
    suite_update.add_argument('--desc', help='Neue Beschreibung')
    suite_update.add_argument('--tags', nargs='*', help='Neue Tags (space-separated)')

    # test case-add
    case_add = test_subparsers.add_parser('case-add', help='Test Case hinzufügen')
    case_add.add_argument('suite_id', type=int, help='Test Suite ID')
    case_add.add_argument('name', help='Test Case Name')
    case_add.add_argument('command', help='Command to execute')
    case_add.add_argument('--desc', help='Beschreibung')
    case_add.add_argument('--cwd', help='Working directory')
    case_add.add_argument('--timeout', type=int, default=300, help='Timeout in seconds (default: 300)')
    case_add.add_argument('--exit-code', type=int, default=0, help='Expected exit code (default: 0)')
    case_add.add_argument('--priority', choices=['critical', 'high', 'normal', 'low'],
                         default='normal', help='Priority level')
    case_add.add_argument('--tags', nargs='*', help='Tags (space-separated)')

    # test case-list
    case_list = test_subparsers.add_parser('case-list', help='Test Cases auflisten')
    case_list.add_argument('--suite', type=int, help='Filter nach Suite ID')
    case_list.add_argument('--priority', help='Filter nach Priority')
    case_list.add_argument('--all', action='store_true', help='Auch inaktive Cases')

    # test case-update
    case_update = test_subparsers.add_parser('case-update', help='Test Case aktualisieren')
    case_update.add_argument('test_case_id', type=int, help='Test Case ID')
    case_update.add_argument('--name', help='Neuer Name')
    case_update.add_argument('--command', help='Neuer Command')
    case_update.add_argument('--desc', help='Neue Beschreibung')
    case_update.add_argument('--cwd', help='Neues Working directory')
    case_update.add_argument('--timeout', type=int, help='Neuer Timeout in seconds')
    case_update.add_argument('--exit-code', type=int, help='Neuer Expected exit code')
    case_update.add_argument('--priority', choices=['critical', 'high', 'normal', 'low'],
                         help='Neue Priority')
    case_update.add_argument('--tags', nargs='*', help='Neue Tags (space-separated)')

    # test exec
    test_exec = test_subparsers.add_parser('exec', help='Test Case ausführen')
    test_exec.add_argument('test_case_id', type=int, help='Test Case ID')
    test_exec.add_argument('--save-output', action='store_true', default=True,
                          help='Speichere vollständigen Output (default: True)')
    test_exec.add_argument('--env', nargs='*', help='Environment variables (KEY=VALUE)')

    # test run-suite
    run_suite = test_subparsers.add_parser('run-suite', help='Alle Tests einer Suite ausführen')
    run_suite.add_argument('suite_id', type=int, help='Test Suite ID')
    run_suite.add_argument('--priority', help='Nur Tests mit dieser Priority')
    run_suite.add_argument('--stop-on-fail', action='store_true',
                          help='Bei erstem Fehler stoppen')

    # test history
    test_history = test_subparsers.add_parser('history', help='Execution History anzeigen')
    test_history.add_argument('test_case_id', type=int, help='Test Case ID')
    test_history.add_argument('--limit', '-l', type=int, default=10,
                             help='Anzahl Einträge (default: 10)')

    # test stats
    test_stats = test_subparsers.add_parser('stats', help='Test Statistiken')
    test_stats.add_argument('--suite', type=int, help='Suite ID')
    test_stats.add_argument('--case', type=int, help='Test Case ID')
    test_stats.add_argument('--project', '-p', help='Projekt Name')
    test_stats.add_argument('--days', type=int, default=30, help='Zeitraum in Tagen (default: 30)')

    # test failures
    test_failures = test_subparsers.add_parser('failures', help='Letzte Fehler anzeigen')
    test_failures.add_argument('--project', '-p', help='Filter nach Projekt')
    test_failures.add_argument('--limit', '-l', type=int, default=10,
                              help='Anzahl Einträge (default: 10)')

    # test flaky
    test_flaky = test_subparsers.add_parser('flaky', help='Flaky Tests identifizieren')
    test_flaky.add_argument('--project', '-p', help='Filter nach Projekt')
    test_flaky.add_argument('--min-runs', type=int, default=5,
                           help='Minimum Anzahl Runs (default: 5)')

    # test coverage
    test_coverage = test_subparsers.add_parser('coverage', help='Test Coverage anzeigen')
    test_coverage.add_argument('project', help='Projekt Name')


def _add_infra_commands(subparsers):
    """Infrastructure management commands"""
    infra_parser = subparsers.add_parser('infra', help='Infrastructure Management (SSH Hosts & Services)')
    infra_subparsers = infra_parser.add_subparsers(dest='infra_command', help='Infra Subcommands')

    # ========== HOST COMMANDS ==========

    # infra add-host
    add_host = infra_subparsers.add_parser('add-host', help='SSH Host hinzufügen')
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
    list_hosts = infra_subparsers.add_parser('list-hosts', help='SSH Hosts auflisten')
    list_hosts.add_argument('--scope', choices=['global', 'project'], help='Filter by scope')
    list_hosts.add_argument('--location', '-l', choices=['local', 'extern'],
                           help='Filter by location')
    list_hosts.add_argument('--project', '-p', help='Filter by project')
    list_hosts.add_argument('--tags', '-t', nargs='+', help='Filter by tags')
    list_hosts.add_argument('--minimal', '-m', action='store_true',
                           help='Minimal output (hostname, location, tags only)')

    # infra show-host
    show_host = infra_subparsers.add_parser('show-host', help='Host Details anzeigen')
    show_host.add_argument('hostname', help='Hostname')

    # infra edit-host
    edit_host = infra_subparsers.add_parser('edit-host', help='Host bearbeiten')
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
    delete_host = infra_subparsers.add_parser('delete-host', help='Host löschen')
    delete_host.add_argument('hostname', help='Hostname to delete')
    delete_host.add_argument('--force', '-f', action='store_true',
                            help='Force deletion even if services exist')

    # ========== SERVICE COMMANDS ==========

    # infra add-service
    add_service = infra_subparsers.add_parser('add-service', help='Service hinzufügen')
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
    list_services = infra_subparsers.add_parser('list-services', help='Services auflisten')
    list_services.add_argument('--host', help='Filter by hostname')
    list_services.add_argument('--env', '-e', choices=['prod', 'staging', 'dev', 'test'],
                              help='Filter by environment')
    list_services.add_argument('--scope', choices=['global', 'project'], help='Filter by scope')
    list_services.add_argument('--project', '-p', help='Filter by project')

    # infra edit-service
    edit_service = infra_subparsers.add_parser('edit-service', help='Service bearbeiten')
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
    delete_service = infra_subparsers.add_parser('delete-service', help='Service löschen')
    delete_service.add_argument('hostname', help='Hostname')
    delete_service.add_argument('service_name', help='Service name to delete')


def _add_setup_commands(subparsers):
    """Setup and diagnostics commands (run without DB connection)"""
    subparsers.add_parser('init', help='Interactive setup wizard (configure DB, start Docker)')
    subparsers.add_parser('doctor', help='Check prerequisites and system health')
    subparsers.add_parser('setup-mcp', help='Configure MCP server in ~/.claude.json')
