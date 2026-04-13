"""
Command Handlers
Implements all 22 command handlers, orchestrating managers.

Architecture: CLI Layer (depends on all lower layers)
"""

import sys
import json
from datetime import datetime
from pathlib import Path

# Import all managers we need to orchestrate
from ..core.database import Database
from ..core.config import Config
from ..domain.actions import ActionManager
from ..domain.search import SearchManager
from ..domain.session import SessionManager
from ..features.snippets import SnippetManager
from ..features.ai_instructions import AIInstructionManager
from ..features.indexing import IndexingManager
from ..features.stats import StatsManager
from ..features.cleanup import CleanupManager
from ..features.todos import TodoManager
from ..features.test_management import TestManager
from ..features.test_runner import TestRunner
from ..features.test_reporting import TestReporter
from ..features.infrastructure import InfrastructureManager


class CommandHandlers:
    """
    Orchestrates all command handlers.

    Responsibility: Glue code between CLI args and business logic.
    Does NOT contain business logic itself.
    """

    def __init__(self, db: Database, config: Config):
        """
        Initialize all managers.

        Args:
            db: Database instance
            config: Config instance
        """
        self.db = db
        self.config = config

        # Initialize optional integrations
        self.duplicate_detector = self._init_duplicate_detector()
        self.token_tracker = self._init_token_tracker()
        self.git_integration = self._init_git_integration()

        # Initialize managers
        self.actions = ActionManager(db, self.duplicate_detector)
        self.search = SearchManager(db, self.token_tracker)
        self.session = SessionManager(db)
        self.snippets = SnippetManager(db)
        self.ai_instructions = AIInstructionManager(db)
        self.stats = StatsManager(db)
        self.cleanup = CleanupManager(db)
        self.todos = TodoManager(db)
        self.test_manager = TestManager(db)
        self.test_runner = TestRunner(db)
        self.test_reporter = TestReporter(db)
        self.infrastructure = InfrastructureManager(db)

        # Indexing needs save callback from actions
        self.indexing = IndexingManager(
            db,
            save_callback=self.actions.save,
            custom_keywords=config.get_keywords()
        )

    def _init_duplicate_detector(self):
        """Initialize DuplicateDetector if available"""
        try:
            from ..domain.duplicate_detection import DuplicateDetectionManager as DuplicateDetector
            detector = DuplicateDetector(self.db.conn)
            detector.create_relations_table()
            return detector
        except Exception as e:
            import sys
            print(f"⚠️  DuplicateDetector init failed: {e}", file=sys.stderr)
            return None

    def _init_token_tracker(self):
        """Initialize TokenTracker if available"""
        try:
            from ..features.token_tracking import TokenTracker
            return TokenTracker()
        except ImportError:
            return None

    def _init_git_integration(self):
        """Initialize GitIntegration if available"""
        try:
            from src.features.git_integration import GitIntegration
            return GitIntegration()
        except ImportError:
            return None

    # ==================== CORE COMMANDS ====================

    def handle_save(self, args):
        action_id = self.actions.save(
            args.content,
            action_type=args.type or 'general',
            project=args.project,
            metadata=args.metadata
        )

        if action_id > 0:
            print(f"✅ Gespeichert (ID: {action_id})")

            # Check for git hook
            if self.git_integration and not hasattr(self, '_git_check_done'):
                self._git_check_done = True
                try:
                    self.git_integration.check_and_prompt()
                except Exception:
                    pass

    def handle_index(self, args):
        count = self.indexing.index_md_files(args.directory)
        print(f"\n✅ {count} MD-Dateien indexiert")

    def handle_session(self, args):
        from datetime import datetime

        project_name = Path.cwd().name
        entries = self.session.get_session(args.id, args.verbose, project_name)

        if not entries:
            print("Keine Einträge in dieser Session")
            return

        print(f"\n📅 Session: {args.id or datetime.now().strftime('%Y%m%d_%H')}\n")

        for entry in entries:
            timestamp = datetime.fromtimestamp(entry['timestamp']).strftime('%H:%M')
            print(f"[{timestamp}] [{entry['type']}] {entry['summary']}")

            if args.verbose and 'content' in entry:
                print(f"    {entry['content'][:200]}")
                print()

    def handle_stats(self, args):
        stats = self.stats.get_stats()

        print("\n📊 Context Manager Statistiken\n")
        print(f"Backend:   {stats.get('backend', 'unknown').upper()}")
        print(f"Projekte:  {stats['projects']}")
        print(f"Actions:   {stats['actions']}")
        print(f"Sessions:  {stats['sessions']}")
        print(f"Types:     {stats['types']}")

        if stats.get('total_tokens') and stats['total_tokens'] is not None:
            print(f"Tokens:    {stats['total_tokens']:,}")

        db_size_mb = stats['db_size'] / (1024 * 1024)
        print(f"DB Size:   {db_size_mb:.2f} MB")
        print()

    def handle_tool_stats(self, args):
        """Handle tool-stats command for MCP tool usage analytics"""
        days = getattr(args, 'days', 30)
        export_format = getattr(args, 'export', None)

        stats = self.stats.get_mcp_tool_stats(days=days, export_format=export_format)

        # If export format is specified, print the export data
        if export_format:
            print(stats)
            return

        # Otherwise, pretty-print the stats
        print(f"\n📊 MCP Tool Usage Stats (Last {stats['time_range_days']} Days)\n")
        print(f"Total Calls:   {stats['total_calls']}")
        print(f"Unique Tools:  {stats['unique_tools']}")
        print()

        if stats['tools']:
            print("🔥 Tool Usage:")
            print(f"{'Tool Name':<30} {'Calls':<8} {'Avg Duration':<15} {'Avg Size':<12} {'Success %':<10}")
            print("-" * 85)
            for tool in stats['tools']:
                print(f"{tool['tool_name']:<30} {tool['calls']:<8} {tool['avg_duration_ms']:<15.2f} {tool['avg_response_kb']:<12.2f} {tool['success_rate']:<10.1f}")

        if stats['unused_tools']:
            print(f"\n❌ Unused Tools ({len(stats['unused_tools'])}):")
            for tool in stats['unused_tools']:
                print(f"  • {tool}")

            # Optimization suggestion
            token_savings = len(stats['unused_tools']) * 600  # Rough estimate
            print(f"\n💡 Optimization Tip:")
            print(f"   Remove {len(stats['unused_tools'])} unused tools to save ~{token_savings:,} tokens per session")

        print()

    def handle_search(self, args):
        from datetime import datetime

        # Handle --date shorthand
        date_from = args.date_from or args.date
        date_to = args.date_to or args.date

        # Handle --all flag
        project = None if args.all else (args.project or 'current')

        results = self.search.search(
            args.query,
            type_filter=args.type,
            limit=args.limit,
            days_back=args.days,
            project=project,
            date_from=date_from,
            date_to=date_to
        )

        if not results:
            print("Keine Ergebnisse gefunden")
            return

        print(f"\n🔍 Gefunden: {len(results)} Einträge\n")

        for entry in results:
            timestamp = datetime.fromtimestamp(entry['timestamp']).strftime('%Y-%m-%d %H:%M')
            print(f"#{entry['id']} | {timestamp} | [{entry['type']}] {entry['project']}")
            print(f"   {entry['snippet']}")
            print()

    def handle_smart_search(self, args):
        """Handle smart-search command - Universal search across all content types"""
        from ..features.smart_search import SmartSearchManager

        # Initialize SmartSearchManager
        smart_search = SmartSearchManager(
            database=self.db,
            ai_instruction_manager=self.ai_instructions,
            snippet_manager=self.snippets,
            search_manager=self.search
        )

        # Perform search
        results = smart_search.search(
            query=args.query,
            limit_per_type=args.per_type,
            total_limit=args.limit,
            include_types=args.types
        )

        counts = results['counts']

        if counts['total'] == 0:
            print("Keine Ergebnisse gefunden")
            return

        # Show summary
        print(f"\n🔍 Universal Search: '{args.query}'")
        print(f"{'=' * 60}")
        print(f"📊 Results: {counts['instructions']} instructions, {counts['snippets']} snippets, {counts['actions']} actions")
        print(f"🎯 Top {counts['ranked_total']} ranked results:\n")

        # Display ranked results
        for i, result in enumerate(results['ranked_all'], 1):
            content_type = result['content_type']
            score = result['final_score']

            # Type icon
            type_icons = {
                'instruction': '📜',
                'snippet': '💾',
                'action': '📊'
            }
            icon = type_icons.get(content_type, '📄')

            # Display based on content type
            if content_type == 'instruction':
                priority_icon = {"must": "🔴", "should": "🟡", "nice": "🟢"}.get(result.get('priority'), "⚪")
                cat = f"[{result.get('category')}]" if result.get('category') else ""
                print(f"{i}. {icon} {priority_icon} Instruction #{result['id']} {cat} (score: {score:.1f})")
                print(f"   {result.get('instruction', '')[:100]}")

            elif content_type == 'snippet':
                print(f"{i}. {icon} Snippet: {result.get('name')} ({result.get('file_type', 'unknown')}) (score: {score:.1f})")
                print(f"   {result.get('description', 'No description')[:100]}")

            elif content_type == 'action':
                print(f"{i}. {icon} Action #{result['id']} [{result.get('type')}] (score: {score:.1f})")
                print(f"   {result.get('summary', result.get('snippet', ''))[:100]}")

            print()

    def handle_show(self, args):
        from datetime import datetime

        entry = self.actions.get_entry(args.entry_id)

        if not entry:
            print(f"❌ Entry #{args.entry_id} nicht gefunden")
            return

        print(f"\n📋 Entry #{entry['id']}")
        print(f"{'=' * 50}")
        print(f"📅 Datum:    {entry['created_at']}")
        print(f"📁 Projekt:  {entry['project']}")
        print(f"🏷️  Typ:      [{entry['type']}]")
        print(f"📊 Session:  {entry['session_id']}")
        print(f"📝 Summary:  {entry['summary']}")

        if entry['content']:
            print(f"\n💬 Vollständiger Inhalt:")
            print(f"{'─' * 50}")
            print(entry['content'])
            print(f"{'─' * 50}")

        print()

    def handle_projects(self, args):
        from datetime import datetime

        projects = self.search.list_projects()

        if not projects:
            print("Keine Projekte gefunden")
            return

        print("\n📁 Projekte:\n")

        for proj in projects:
            if proj['last_activity']:
                last_activity = datetime.fromtimestamp(proj['last_activity']).strftime('%Y-%m-%d')
            else:
                last_activity = "never"
            print(f"{proj['name']:30} | {proj['action_count']:4} actions | last: {last_activity}")

        print()

    def handle_vacuum(self, args):
        print("🧹 Optimiere Datenbank...")
        self.stats.vacuum()
        print("✅ Datenbank optimiert!")

    def handle_cleanup(self, args):
        if args.stats:
            stats = self.cleanup.get_file_tracking_stats()
            print("\n📊 File Tracking Statistics:\n")
            print(f"  Total indexed entries:     {stats['total']}")
            print(f"  With file tracking:        {stats['tracked']} ({stats['tracked_pct']:.1f}%)")
            print(f"  With hash:                 {stats['hashed']} ({stats['hashed_pct']:.1f}%)")
            print(f"  Orphaned (file deleted):   {stats['orphaned']}")
            print(f"  Legacy (no tracking):      {stats['legacy']}\n")
            return

        if args.legacy:
            entries = self.cleanup.find_legacy_entries()
            if not entries:
                print("✅ No legacy entries found - all indexed content has file tracking!")
                return

            print(f"\n📜 {len(entries)} Legacy Entries (without file tracking):\n")
            for entry in entries[:20]:
                print(f"  [{entry['id']}] {entry['action_type']}: {entry['summary'][:60]}...")

            if len(entries) > 20:
                print(f"\n  ... and {len(entries) - 20} more")
            print()
            return

        if args.orphaned:
            entries = self.cleanup.find_orphaned_entries()
            if not entries:
                print("✅ No orphaned entries found - all files still exist!")
                return

            print(f"\n🗑️  {len(entries)} Orphaned Entries (files deleted):\n")
            for entry in entries:
                print(f"  [{entry['id']}] {entry['project']}/{entry['action_type']}: {Path(entry['source_file']).name}")

            if not args.force:
                response = input(f"\n❓ Delete these {len(entries)} orphaned entries? (y/n): ")
                if response.lower() != 'y':
                    print("❌ Abgebrochen")
                    return

            deleted = self.cleanup.delete_entries([e['id'] for e in entries])
            print(f"✅ {deleted} orphaned entries deleted")
            print("\n💡 Run 'cm vacuum' to reclaim disk space")
            return

        if args.normalize_sessions:
            updated = self.cleanup.normalize_cross_project_sessions()
            if updated == 0:
                print("✅ No cross-project sessions detected")
            else:
                print(f"✅ Normalized {updated} session entries across projects")
            return

        if args.sessions:
            sessions = self.cleanup.find_cross_project_sessions()
            if not sessions:
                print("✅ Keine Sessions mit mehreren Projekten gefunden")
                return

            print(f"\n🧭 {len(sessions)} Sessions teilen sich mehrere Projekte:\n")
            for session in sessions[:20]:
                projects = ', '.join(session['projects'])
                print(
                    f"  Session {session['session_id']} → {projects} "
                    f"({session['action_count']} Aktionen)"
                )

            if len(sessions) > 20:
                print(f"\n  ... und {len(sessions) - 20} weitere")
            print("\n💡 Run 'cm cleanup --normalize-sessions' to separate them per project")
            return

        # If no specific flag, show stats
        print("Usage: cm cleanup [--stats|--orphaned|--legacy|--sessions|--normalize-sessions]")
        print("  --stats                 Show file tracking statistics")
        print("  --orphaned              Remove entries whose files were deleted")
        print("  --legacy                List entries without file tracking")
        print("  --sessions              List sessions spanning multiple projects")
        print("  --normalize-sessions    Assign project-specific session IDs")

    def handle_tokens(self, args):
        if not self.token_tracker:
            print("❌ TokenTracker nicht verfügbar")
            return

        self.token_tracker.print_summary()

    # ==================== SNIPPET COMMANDS ====================

    def handle_snippet_add(self, args):
        """Handle snippet-add command"""
        try:
            snippet_id = self.snippets.add(
                args.file_path,
                name=args.name,
                description=args.desc,
                tags=args.tags,
                store_content=args.store
            )
            print(f"✅ Snippet gespeichert (ID: {snippet_id})")
        except FileNotFoundError as e:
            print(f"❌ {e}")
            sys.exit(1)

    def handle_snippet_search(self, args):
        """Handle snippet-search command"""
        results = self.snippets.search(
            query=args.query,
            file_type=args.type,
            tags=args.tags,
            limit=args.limit
        )

        if not results:
            print("Keine Snippets gefunden")
            return

        print(f"\n📦 Gefunden: {len(results)} Snippets\n")

        for snippet in results:
            tags_str = ', '.join(snippet['tags']) if snippet['tags'] else ''
            print(f"[{snippet['file_type']}] {snippet['name']}")
            if snippet['description']:
                print(f"    {snippet['description']}")
            if tags_str:
                print(f"    Tags: {tags_str}")
            print(f"    {snippet['line_count']} lines | {snippet['usage_count']} uses")
            print()

    def handle_snippet_show(self, args):
        """Handle snippet-show command"""
        from datetime import datetime

        snippet = self.snippets.get(args.name, full_content=args.cat)

        if not snippet:
            print(f"❌ Snippet '{args.name}' nicht gefunden")
            return

        print(f"\n📦 Snippet: {snippet['name']}\n")
        print(f"Type:        {snippet['file_type']}")
        print(f"Path:        {snippet['file_path']}")

        if snippet['description']:
            print(f"Description: {snippet['description']}")

        if snippet['tags']:
            print(f"Tags:        {', '.join(snippet['tags'])}")

        print(f"Size:        {snippet['file_size']} bytes, {snippet['line_count']} lines")
        print(f"Usage:       {snippet['usage_count']} times")

        if snippet.get('last_used'):
            last_used = datetime.fromtimestamp(snippet['last_used']).strftime('%Y-%m-%d %H:%M')
            print(f"Last used:   {last_used}")

        if snippet.get('key_sections'):
            print(f"\nKey sections:")
            for name, line in snippet['key_sections'].items():
                print(f"  {name:30} {line}")

        if args.cat and snippet.get('content'):
            print(f"\n{'='*60}\n")
            print(snippet['content'])
            print(f"\n{'='*60}\n")

    def handle_snippet_list(self, args):
        """Handle snippet-list command"""
        snippets = self.snippets.list_all()

        if not snippets:
            print("Keine Snippets gefunden")
            return

        print(f"\n📦 {len(snippets)} Snippets:\n")

        for snippet in snippets:
            print(f"[{snippet['file_type']:12}] {snippet['name']:30} ({snippet['line_count']} lines)")

        print()

    def handle_snippet_delete(self, args):
        """Handle snippet-delete command"""
        if not args.force:
            snippet = self.snippets.get(args.name)
            if snippet:
                print(f"Snippet: {snippet['name']} ({snippet['file_type']}, {snippet['line_count']} lines)")
                response = input("Wirklich löschen? (y/n): ")
                if response.lower() != 'y':
                    print("❌ Abgebrochen")
                    return

        if self.snippets.delete(args.name):
            print(f"✅ Snippet '{args.name}' gelöscht")
        else:
            print(f"❌ Snippet '{args.name}' nicht gefunden")

    # ==================== DELETE COMMANDS ====================

    def handle_delete(self, args):
        if not args.force:
            response = input(f"Eintrag #{args.id} wirklich löschen? (y/N) ")
            if response.lower() != 'y':
                print("Abgebrochen")
                return

        if self.actions.delete_entry(args.id):
            print("✅ Eintrag gelöscht")
        else:
            print(f"❌ Eintrag #{args.id} nicht gefunden")

    def handle_project_delete(self, args):
        """Handle project-delete command"""
        if not args.force:
            response = input(f"Projekt '{args.name}' mit ALLEN Daten löschen? (y/N) ")
            if response.lower() != 'y':
                print("Abgebrochen")
                return

        result = self.actions.delete_project(args.name)

        if not result:
            print(f"❌ Projekt '{args.name}' nicht gefunden")
        else:
            print("✅ Projekt gelöscht")

    def handle_related(self, args):
        related = self.actions.get_related_entries(args.id, args.limit)

        if not related:
            print(f"Keine verwandten Einträge für #{args.id} gefunden")
            return

        print(f"\n🔗 Verwandte Einträge für #{args.id}:\n")

        for entry in related:
            similarity = f"{entry['similarity_score']:.0%}"
            print(f"#{entry['target_id']} ({similarity}) - {entry['relation_type']}")
            if 'content' in entry:
                print(f"   {entry['content'][:100]}")
            print()

    # ==================== GIT COMMANDS ====================

    def handle_git_init(self, args):
        """Handle git-init command"""
        if not self.git_integration:
            print("❌ GitIntegration nicht verfügbar")
            return

        try:
            if args.global_template:
                print("🔧 Installiere Git-Hook global...")
                print("❌ Global installation noch nicht implementiert")
            else:
                if self.git_integration.install_hook(force=args.force):
                    print("✅ Git-Hook installiert!")
                else:
                    print("❌ Installation fehlgeschlagen")
        except Exception as e:
            print(f"❌ Fehler: {e}")

    def handle_git_info(self, args):
        """Handle git-info command"""
        if not self.git_integration:
            print("❌ GitIntegration nicht verfügbar")
            return

        info = self.git_integration.get_git_info()

        if not info:
            print("❌ Kein Git-Repository gefunden")
            return

        print(f"\n📚 Git Repository Info:\n")
        print(f"Branch:       {info['branch']}")
        print(f"Last Commit:  {info['last_commit']}")
        print(f"Repo Name:    {info['repo_name']}")
        print(f"Has Changes:  {'Ja' if info['has_changes'] else 'Nein'}")
        print()

    def handle_commit_info(self, args):
        """Handle commit-info command"""
        cursor = self.db.conn.cursor()

        if args.last:
            cursor.execute("""
                SELECT a.id, a.summary, a.metadata, a.timestamp
                FROM actions a
                JOIN action_types at ON a.type_id = at.id
                WHERE at.name = 'commit'
                ORDER BY a.timestamp DESC
                LIMIT ?
            """, (args.last,))

            commits = cursor.fetchall()
            if not commits:
                print("Keine Commits gefunden")
                return

            print(f"\n📚 Letzte {len(commits)} Commits:\n")
            for commit in commits:
                metadata = json.loads(commit['metadata']) if commit['metadata'] else {}
                commit_hash = metadata.get('commit_hash', 'unknown')[:8]
                timestamp = datetime.fromtimestamp(commit['timestamp']).strftime('%Y-%m-%d %H:%M')
                message = commit['summary'].replace('Git commit: ', '')
                print(f"{commit_hash} - {timestamp}")
                print(f"  {message}\n")
            return

        if args.hash:
            cursor.execute("""
                SELECT a.id, a.summary, a.metadata, a.timestamp
                FROM actions a
                JOIN action_types at ON a.type_id = at.id
                WHERE at.name = 'commit'
                    AND json_extract(a.metadata, '$.commit_hash') LIKE ?
                ORDER BY a.timestamp DESC
                LIMIT 1
            """, (f"{args.hash}%",))
        elif args.id:
            cursor.execute("""
                SELECT a.id, a.summary, a.metadata, a.timestamp
                FROM actions a
                JOIN action_types at ON a.type_id = at.id
                WHERE a.id = ? AND at.name = 'commit'
            """, (args.id,))
        else:
            print("❌ Bitte --hash, --last oder ID angeben")
            return

        commit = cursor.fetchone()
        if not commit:
            print("❌ Commit nicht gefunden")
            return

        metadata = json.loads(commit['metadata']) if commit['metadata'] else {}

        print(f"\n📚 Commit Details:\n")
        print(f"Entry ID:     #{commit['id']}")
        print(f"Hash:         {metadata.get('commit_hash', 'unknown')}")
        print(f"Branch:       {metadata.get('branch', 'unknown')}")
        print(f"Author:       {metadata.get('author', 'unknown')}")
        print(f"Timestamp:    {metadata.get('timestamp', 'unknown')}")
        print(f"\nMessage:      {commit['summary'].replace('Git commit: ', '')}")

        if metadata.get('message_body'):
            print(f"\nBody:\n{metadata['message_body']}\n")

        if metadata.get('files_changed'):
            files = metadata['files_changed'].split()
            print(f"Files changed: {len(files)}")
            for f in files[:10]:
                print(f"  - {f}")
            if len(files) > 10:
                print(f"  ... and {len(files) - 10} more")

        if metadata.get('stats'):
            print(f"\nStats: {metadata['stats']}")

        print()

    # ==================== AI COMMANDS ====================

    def handle_ai_prompt(self, args):
        """Handle ai-prompt command"""
        try:
            from ..features.ai_prompt import AIPromptManager

            # Initialize with proper dependency injection
            ai_prompt = AIPromptManager(
                search_manager=self.search,
                session_manager=SessionManager(self.db),
                snippet_manager=self.snippets,
                ai_instruction_manager=self.ai_instructions,
                git_integration=self.git_integration
            )

            if args.quick:
                prompt = ai_prompt.generate_quick_start(project=args.project)
            else:
                prompt = ai_prompt.generate_session_prompt(
                    project=args.project,
                    verbose=args.verbose,
                    smart=args.smart if hasattr(args, 'smart') else False,
                    hours=args.hours if hasattr(args, 'hours') else 24
                )

            print(prompt)
        except ImportError as e:
            print(f"❌ AIPromptManager nicht verfügbar: {e}")
        except Exception as e:
            import traceback
            print(f"❌ Fehler: {e}")
            traceback.print_exc()

    def handle_ai_instruction(self, args):
        """Handle ai-instruction command"""
        if args.show:
            instructions = self.ai_instructions.get(scope='all', project=args.project)
            inst = next((i for i in instructions if i['id'] == args.show), None)

            if not inst:
                print(f"❌ Instruction #{args.show} nicht gefunden")
                return

            scope_icon = {'global': '🌍', 'project': '📁', 'session': '⏱️'}.get(inst['scope'], '')
            priority_icon = {'must': '🔴', 'should': '🟡', 'nice': '🟢'}.get(inst['priority'], '')
            status = "✅ Aktiv" if inst['active'] else "❌ Inaktiv"

            print(f"\n🤖 KI-Anweisung #{inst['id']}\n")
            print(f"Status:     {status}")
            print(f"Scope:      {scope_icon} {inst['scope']}")
            print(f"Priority:   {priority_icon} {inst['priority']}")
            print(f"Category:   {inst['category'] or 'general'}")
            print(f"\nInstruction:\n{inst['instruction']}\n")

            if inst.get('rationale'):
                print(f"Rationale:\n{inst['rationale']}\n")

            if inst.get('examples'):
                import json
                try:
                    examples = json.loads(inst['examples'])
                    if examples.get('good'):
                        print(f"✅ Good Example: {examples['good']}")
                    if examples.get('bad'):
                        print(f"❌ Bad Example: {examples['bad']}")
                    print()
                except:
                    pass

        elif args.list:
            instructions = self.ai_instructions.get(scope='all', project=args.project)

            if not instructions:
                print("Keine Anweisungen gefunden")
                return

            print(f"\n🤖 KI-Anweisungen ({len(instructions)}):\n")

            for inst in instructions:
                scope_icon = {'global': '🌍', 'project': '📁', 'session': '⏱️'}.get(inst['scope'], '')
                priority_icon = {'must': '🔴', 'should': '🟡', 'nice': '🟢'}.get(inst['priority'], '')

                status = "✅" if inst['active'] else "❌"
                print(f"{status} #{inst['id']} {scope_icon} {priority_icon} [{inst['category'] or 'general'}]")
                print(f"   {inst['instruction'][:80]}")
                print()

        elif args.delete is not None:
            instruction = self.ai_instructions.get_by_id(args.delete)

            if not instruction:
                print(f"❌ Instruction #{args.delete} nicht gefunden")
                return

            if not args.force:
                preview = instruction['instruction'][:80]
                try:
                    confirm = input(
                        f"⚠️  Instruction #{args.delete} wirklich löschen?\n   {preview}\n   Bestätigen mit 'y': "
                    )
                except EOFError:
                    print("❌ Löschung abgebrochen (keine Eingabe möglich)")
                    return

                if confirm.lower() not in ('y', 'yes', 'j', 'ja'):
                    print("🚫 Löschung abgebrochen")
                    return

            if self.ai_instructions.delete(args.delete):
                print(f"🗑️  Instruction #{args.delete} gelöscht")
            else:
                print(f"❌ Löschung von Instruction #{args.delete} fehlgeschlagen")

        elif args.search:
            # Use advanced search with filters
            results = self.ai_instructions.search_filtered(
                query=args.search,
                category=getattr(args, 'search_category', None),
                priority=getattr(args, 'search_priority', None),
                scope=getattr(args, 'search_scope', None),
                project=args.project
            )

            if not results:
                print("Keine Anweisungen gefunden")
                return

            # Show applied filters
            filters = []
            if args.search:
                filters.append(f"query='{args.search}'")
            if getattr(args, 'search_category', None):
                filters.append(f"category={args.search_category}")
            if getattr(args, 'search_priority', None):
                filters.append(f"priority={args.search_priority}")
            if getattr(args, 'search_scope', None):
                filters.append(f"scope={args.search_scope}")

            filter_str = " | ".join(filters) if filters else "all"
            print(f"\n🔍 Gefunden: {len(results)} Anweisungen ({filter_str})\n")

            for inst in results:
                # Show category and scope
                cat = f"[{inst.get('category', 'N/A')}]" if inst.get('category') else ""
                scope_icon = {'global': '🌍', 'project': '📁', 'session': '⏱️'}.get(inst['scope'], '')

                print(f"#{inst['id']} {scope_icon} [{inst['priority']}] {cat} {inst['instruction'][:80]}")
                if 'snippet' in inst:
                    print(f"   {inst['snippet']}")
                print()

        elif args.toggle is not None:
            new_status = self.ai_instructions.toggle(args.toggle)
            status_str = "aktiviert" if new_status else "deaktiviert"
            print(f"✅ Anweisung #{args.toggle} {status_str}")

        elif args.instruction:
            examples = {}
            if args.example_good:
                examples['good'] = args.example_good
            if args.example_bad:
                examples['bad'] = args.example_bad

            inst_id = self.ai_instructions.save(
                args.instruction,
                scope=args.scope,
                priority=args.priority,
                category=args.category,
                rationale=args.rationale,
                examples=examples if examples else None,
                project=args.project
            )

            print(f"✅ Anweisung gespeichert (ID: {inst_id})")

        else:
            print("❌ Keine Aktion angegeben (--list, --search, --delete, --toggle oder instruction)")

    def handle_ai_instruction_update(self, args):
        """Handle ai-instruction-update command"""
        if args.toggle:
            new_status = self.ai_instructions.toggle(args.id)
            status_text = "aktiviert" if new_status else "deaktiviert"
            print(f"✅ Anweisung #{args.id} {status_text}")
        else:
            update_kwargs = {}

            if args.scope is not None:
                update_kwargs['scope'] = args.scope
            if args.priority is not None:
                update_kwargs['priority'] = args.priority
            if args.category is not None:
                update_kwargs['category'] = args.category
            if args.instruction is not None:
                update_kwargs['instruction'] = args.instruction
            if args.rationale is not None:
                update_kwargs['rationale'] = args.rationale
            if args.clear_rationale:
                update_kwargs['clear_rationale'] = True

            examples_payload = None

            if args.example_good is not None or args.example_bad is not None:
                instruction = self.ai_instructions.get_by_id(args.id)

                if not instruction:
                    print(f"❌ Instruction #{args.id} nicht gefunden")
                    return

                current_examples = {}
                if instruction.get('examples'):
                    try:
                        current_examples = json.loads(instruction['examples']) or {}
                    except Exception:
                        current_examples = {}

                if args.example_good is not None:
                    if args.example_good == "":
                        current_examples.pop('good', None)
                    else:
                        current_examples['good'] = args.example_good

                if args.example_bad is not None:
                    if args.example_bad == "":
                        current_examples.pop('bad', None)
                    else:
                        current_examples['bad'] = args.example_bad

                examples_payload = current_examples if current_examples else None

            if examples_payload is not None:
                update_kwargs['examples'] = examples_payload

            if args.clear_examples:
                update_kwargs['clear_examples'] = True

            if not update_kwargs:
                print("❌ Keine Updates angegeben")
                return

            if self.ai_instructions.update(args.id, **update_kwargs):
                print(f"✅ Anweisung #{args.id} aktualisiert")
            else:
                print(f"❌ Update fehlgeschlagen")

    # ==================== TODO COMMANDS ====================

    def handle_todo(self, args):
        """Handle todo command with subcommands"""
        if not args.todo_command:
            print("❌ Kein TODO Subcommand angegeben")
            print("Verfügbare Commands: add, list, done, start, reopen, cancel, delete, show, stats, stale, suggest")
            return

        todo_handlers = {
            'add': self.handle_todo_add,
            'list': self.handle_todo_list,
            'done': self.handle_todo_done,
            'start': self.handle_todo_start,
            'reopen': self.handle_todo_reopen,
            'cancel': self.handle_todo_cancel,
            'delete': self.handle_todo_delete,
            'show': self.handle_todo_show,
            'stats': self.handle_todo_stats,
            'stale': self.handle_todo_stale,
            'suggest': self.handle_todo_suggest,
        }

        handler = todo_handlers.get(args.todo_command)
        if handler:
            handler(args)
        else:
            print(f"❌ Unbekanntes TODO Command: {args.todo_command}")

    def handle_todo_add(self, args):
        """Add new TODO"""
        try:
            todo_id = self.todos.add_todo(
                summary=args.summary,
                content=args.content,
                priority=args.priority,
                category=args.category,
                due_date=args.due,
                tags=args.tags,
                project_name=args.project,
                depends_on=args.depends,
                assigned_to=args.assign
            )
            print(f"✅ TODO erstellt (ID: {todo_id})")

            # Show priority indicator
            priority_icons = {'high': '🔴', 'normal': '🟡', 'low': '🟢'}
            print(f"   {priority_icons.get(args.priority, '')} Priorität: {args.priority}")

            if args.category:
                print(f"   📁 Kategorie: {args.category}")
            if args.due:
                print(f"   📅 Fällig: {args.due}")
            if args.assign:
                print(f"   👤 Zugewiesen: {args.assign}")

        except Exception as e:
            print(f"❌ Fehler: {e}")

    def handle_todo_list(self, args):
        """List TODOs with filters"""
        if args.all_projects:
            project_filter = None
        else:
            project_filter = args.project or Path.cwd().name

        todos = self.todos.list_todos(
            status=args.status,
            project_name=project_filter,
            priority=args.priority,
            category=args.category,
            assigned_to=args.assigned,
            include_done=args.all,
            limit=args.limit
        )

        if not todos:
            print("Keine TODOs gefunden")
            return

        scope = "alle Projekte" if args.all_projects else project_filter
        print(f"\n📋 TODOs ({len(todos)} Einträge | Projekt: {scope}):\n")

        priority_icons = {'high': '🔴', 'normal': '🟡', 'low': '🟢'}
        status_icons = {
            'open': '⭕',
            'in_progress': '🔄',
            'done': '✅',
            'cancelled': '❌'
        }

        for todo in todos:
            # Header line
            status_icon = status_icons.get(todo['status'], '')
            priority_icon = priority_icons.get(todo['priority'], '')

            print(f"{status_icon} #{todo['id']} {priority_icon} {todo['summary']}")

            # Details
            details = []
            if todo['category']:
                details.append(f"[{todo['category']}]")
            if todo['due_date']:
                details.append(f"📅 {todo['due_date']}")
            if todo['assigned_to']:
                details.append(f"👤 {todo['assigned_to']}")
            if todo['status'] == 'done' and todo['completed_at']:
                details.append(f"✓ {todo['completed_at']}")

            if details:
                print(f"   {' | '.join(details)}")

            # Content is optional (not in v_todos view)
            if todo.get('content') and todo['content'] != todo['summary']:
                print(f"   {todo['content'][:100]}...")

            print()

    def handle_todo_done(self, args):
        """Mark TODOs as done"""
        result = self.todos.mark_done(args.ids, force=args.force)

        if result['success']:
            print(f"✅ Erledigt: {', '.join(map(str, result['success']))}")

        if result['failed']:
            print("\n❌ Fehlgeschlagen:")
            for fail in result['failed']:
                print(f"   #{fail['id']}: {fail['error']}")

    def handle_todo_start(self, args):
        """Mark TODO as in_progress"""
        try:
            self.todos.update_status(args.id, 'in_progress')
            print(f"🔄 TODO #{args.id} wird bearbeitet")
        except Exception as e:
            print(f"❌ Fehler: {e}")

    def handle_todo_reopen(self, args):
        """Reopen completed TODOs"""
        result = self.todos.reopen(args.ids)

        if result['success']:
            print(f"⭕ Wiedereröffnet: {', '.join(map(str, result['success']))}")

        if result['failed']:
            print("\n❌ Fehlgeschlagen:")
            for fail in result['failed']:
                print(f"   #{fail['id']}: {fail['error']}")

    def handle_todo_cancel(self, args):
        """Cancel TODOs"""
        success = []
        failed = []

        for todo_id in args.ids:
            try:
                self.todos.update_status(todo_id, 'cancelled')
                success.append(todo_id)
            except Exception as e:
                failed.append({'id': todo_id, 'error': str(e)})

        if success:
            print(f"❌ Abgebrochen: {', '.join(map(str, success))}")

        if failed:
            print("\n❌ Fehlgeschlagen:")
            for fail in failed:
                print(f"   #{fail['id']}: {fail['error']}")

    def handle_todo_delete(self, args):
        """Delete TODOs permanently"""
        if not args.force:
            print(f"⚠️  TODOs permanent löschen: {', '.join(map(str, args.ids))}")
            response = input("Wirklich löschen? (y/n): ")
            if response.lower() != 'y':
                print("Abgebrochen")
                return

        deleted = self.todos.delete_todos(args.ids)
        print(f"🗑️  {deleted} TODO(s) gelöscht")

    def handle_todo_show(self, args):
        """Show TODO details"""
        todos = self.todos.list_todos(limit=1)

        # Find the specific TODO
        todo = None
        for t in self.todos.list_todos(include_done=True, limit=1000):
            if t['id'] == args.id:
                todo = t
                break

        if not todo:
            print(f"❌ TODO #{args.id} nicht gefunden")
            return

        # Display details
        print(f"\n📋 TODO #{todo['id']}")
        print("=" * 50)
        print(f"Summary:     {todo['summary']}")
        print(f"Status:      {todo['status']}")
        print(f"Priority:    {todo['priority']}")

        if todo.get('category'):
            print(f"Category:    {todo['category']}")
        if todo.get('project'):
            print(f"Project:     {todo['project']}")
        if todo.get('assigned_to'):
            print(f"Assigned to: {todo['assigned_to']}")
        if todo.get('due_date'):
            print(f"Due date:    {todo['due_date']}")
        if todo.get('tags'):
            print(f"Tags:        {', '.join(todo['tags'])}")
        if todo.get('depends_on'):
            print(f"Depends on:  {', '.join(map(str, todo['depends_on']))}")

        print(f"\nCreated:     {todo['created_at']}")
        if todo.get('completed_at'):
            print(f"Completed:   {todo['completed_at']}")
        if todo.get('reopened_count'):
            print(f"Reopened:    {todo['reopened_count']} times")

        if todo.get('content'):
            print(f"\n📝 Details:")
            print("-" * 50)
            print(todo['content'])

    def handle_todo_stats(self, args):
        """Show TODO statistics"""
        stats = self.todos.get_todo_stats(project_name=args.project)

        print("\n📊 TODO Statistiken")
        print("=" * 40)
        print(f"Gesamt: {stats['total']}")

        if stats['by_status']:
            print("\nNach Status:")
            for status, count in stats['by_status'].items():
                print(f"  {status}: {count}")

        if stats['by_priority']:
            print("\nNach Priorität:")
            for priority, count in stats['by_priority'].items():
                print(f"  {priority}: {count}")

        if stats['overdue'] > 0:
            print(f"\n⚠️  Überfällig: {stats['overdue']}")

    def handle_todo_stale(self, args):
        """Show stale TODOs"""
        stale = self.todos.get_stale_todos(days=args.days)

        if not stale:
            print(f"Keine TODOs älter als {args.days} Tage")
            return

        print(f"\n⏰ Alte TODOs (>{args.days} Tage):\n")

        for todo in stale:
            print(f"#{todo['id']} ({todo['days_old']} Tage) - {todo['summary']}")
            if todo['category']:
                print(f"   [{todo['category']}]")
            print()

    def handle_todo_suggest(self, args):
        """Suggest TODOs based on context"""
        suggestions = self.todos.suggest_todos(
            project_name=args.project,
            limit=args.limit
        )

        if not suggestions:
            print("Keine TODO-Vorschläge gefunden")
            return

        print(f"\n💡 TODO Vorschläge:\n")

        for i, suggestion in enumerate(suggestions, 1):
            print(f"{i}. {suggestion['summary']}")
            if suggestion.get('category'):
                print(f"   Kategorie: {suggestion['category']}")
            if suggestion.get('priority'):
                print(f"   Priorität: {suggestion['priority']}")
            print()

    # ========== TEST MANAGEMENT HANDLERS ==========

    def handle_test(self, args):
        """Main test command dispatcher"""
        test_command_map = {
            'suite-add': self.handle_test_suite_add,
            'suite-list': self.handle_test_suite_list,
            'suite-update': self.handle_test_suite_update,
            'case-add': self.handle_test_case_add,
            'case-list': self.handle_test_case_list,
            'case-update': self.handle_test_case_update,
            'exec': self.handle_test_exec,
            'run-suite': self.handle_test_run_suite,
            'history': self.handle_test_history,
            'stats': self.handle_test_stats,
            'failures': self.handle_test_failures,
            'flaky': self.handle_test_flaky,
            'coverage': self.handle_test_coverage,
        }

        if not args.test_command:
            print("❌ Kein Test-Subcommand angegeben")
            print("Verfügbar: suite-add, suite-list, suite-update, case-add, case-list, case-update, exec, run-suite, history, stats, failures, flaky, coverage")
            sys.exit(1)

        handler = test_command_map.get(args.test_command)
        if not handler:
            print(f"❌ Unbekanntes Test-Command: {args.test_command}")
            sys.exit(1)

        handler(args)

    def handle_test_suite_add(self, args):
        """Create new test suite"""
        try:
            project = args.project or self.config.project_name
            suite_id = self.test_manager.create_test_suite(
                name=args.name,
                project_name=project,
                description=args.desc,
                tags=args.tags
            )
            print(f"✅ Test Suite erstellt: ID {suite_id}")
            print(f"   Name: {args.name}")
            print(f"   Projekt: {project}")
        except ValueError as e:
            print(f"❌ Fehler: {e}")
            sys.exit(1)

    def handle_test_suite_list(self, args):
        """List test suites"""
        suites = self.test_manager.list_test_suites(
            project_name=args.project,
            active_only=not args.all
        )

        if not suites:
            print("Keine Test Suites gefunden")
            return

        print(f"\n📋 Test Suites ({len(suites)}):\n")
        for suite in suites:
            status = "✅" if suite['active'] else "⏸️"
            print(f"{status} ID {suite['id']}: {suite['name']}")
            print(f"   Projekt: {suite['project_name']}")
            print(f"   Tests: {suite['test_count']}")
            if suite['description']:
                print(f"   {suite['description'][:80]}...")
            print()

    def handle_test_suite_update(self, args):
        """Update test suite"""
        try:
            # Build update dict from provided args
            updates = {}
            if hasattr(args, 'name') and args.name:
                updates['name'] = args.name
            if hasattr(args, 'desc') and args.desc:
                updates['description'] = args.desc
            if hasattr(args, 'tags') and args.tags:
                updates['tags'] = args.tags

            if not updates:
                print("❌ Keine Updates angegeben")
                print("Verfügbare Optionen: --name, --desc, --tags")
                sys.exit(1)

            success = self.test_manager.update_test_suite(
                suite_id=args.suite_id,
                **updates
            )

            if success:
                print(f"✅ Test Suite {args.suite_id} aktualisiert")
                for key, value in updates.items():
                    print(f"   {key}: {value}")
            else:
                print(f"❌ Keine Änderungen vorgenommen")

        except ValueError as e:
            print(f"❌ Fehler: {e}")
            sys.exit(1)

    def handle_test_case_add(self, args):
        """Add test case to suite"""
        try:
            test_id = self.test_manager.add_test_case(
                suite_id=args.suite_id,
                name=args.name,
                command=args.command,
                description=args.desc,
                working_directory=args.cwd,
                timeout=args.timeout,
                expected_exit_code=args.exit_code,
                tags=args.tags,
                priority=args.priority
            )
            print(f"✅ Test Case erstellt: ID {test_id}")
            print(f"   Name: {args.name}")
            print(f"   Command: {args.command}")
            print(f"   Timeout: {args.timeout}s")
            print(f"   Expected Exit Code: {args.exit_code}")
        except ValueError as e:
            print(f"❌ Fehler: {e}")
            sys.exit(1)

    def handle_test_case_list(self, args):
        """List test cases"""
        tests = self.test_manager.list_test_cases(
            suite_id=args.suite,
            active_only=not args.all,
            priority=args.priority
        )

        if not tests:
            print("Keine Test Cases gefunden")
            return

        print(f"\n🧪 Test Cases ({len(tests)}):\n")
        for test in tests:
            status = "✅" if test['active'] else "⏸️"
            priority_icon = {"critical": "🔴", "high": "🟠", "normal": "🟡", "low": "⚪"}.get(test['priority'], "⚪")
            print(f"{status} {priority_icon} ID {test['id']}: {test['name']}")
            print(f"   Suite: {test['suite_name']}")
            print(f"   Command: {test['command'][:60]}...")
            if test['working_directory']:
                print(f"   Working Dir: {test['working_directory']}")
            print(f"   Timeout: {test['timeout']}s | Expected Exit: {test['expected_exit_code']}")
            print()

    def handle_test_case_update(self, args):
        """Update test case"""
        try:
            # Build update dict from provided args
            updates = {}
            if hasattr(args, 'name') and args.name:
                updates['name'] = args.name
            if hasattr(args, 'command') and args.command:
                updates['command'] = args.command
            if hasattr(args, 'desc') and args.desc:
                updates['description'] = args.desc
            if hasattr(args, 'cwd') and args.cwd:
                updates['working_directory'] = args.cwd
            if hasattr(args, 'timeout') and args.timeout:
                updates['timeout'] = args.timeout
            if hasattr(args, 'exit_code') and args.exit_code is not None:
                updates['expected_exit_code'] = args.exit_code
            if hasattr(args, 'priority') and args.priority:
                updates['priority'] = args.priority
            if hasattr(args, 'tags') and args.tags:
                updates['tags'] = args.tags

            if not updates:
                print("❌ Keine Updates angegeben")
                print("Verfügbare Optionen: --name, --command, --desc, --cwd, --timeout, --exit-code, --priority, --tags")
                sys.exit(1)

            success = self.test_manager.update_test_case(
                test_case_id=args.test_case_id,
                **updates
            )

            if success:
                print(f"✅ Test Case {args.test_case_id} aktualisiert")
                for key, value in updates.items():
                    if key == 'command' and len(str(value)) > 60:
                        print(f"   {key}: {str(value)[:60]}...")
                    else:
                        print(f"   {key}: {value}")
            else:
                print(f"❌ Keine Änderungen vorgenommen")

        except ValueError as e:
            print(f"❌ Fehler: {e}")
            sys.exit(1)

    def handle_test_exec(self, args):
        """Execute a test case"""
        print(f"🧪 Executing test case {args.test_case_id}...")

        # Parse environment variables
        env = {}
        if args.env:
            for env_var in args.env:
                if '=' in env_var:
                    key, value = env_var.split('=', 1)
                    env[key] = value

        try:
            result = self.test_runner.execute_test_case(
                test_case_id=args.test_case_id,
                environment=env if env else None,
                save_full_output=args.save_output
            )

            # Display result
            status_icon = {"passed": "✅", "failed": "❌", "timeout": "⏱️", "error": "🚨"}.get(result.status, "❓")
            print(f"\n{status_icon} Test {result.status.upper()}")
            print(f"Duration: {result.duration_ms}ms")
            print(f"Exit Code: {result.exit_code}")

            if result.stdout:
                print(f"\n📤 STDOUT:\n{result.stdout[:500]}")
            if result.stderr:
                print(f"\n📛 STDERR:\n{result.stderr[:500]}")
            if result.error_message:
                print(f"\n⚠️  Error: {result.error_message}")

        except ValueError as e:
            print(f"❌ Fehler: {e}")
            sys.exit(1)

    def handle_test_run_suite(self, args):
        """Run all tests in a suite"""
        # Get test cases
        tests = self.test_manager.list_test_cases(
            suite_id=args.suite_id,
            active_only=True,
            priority=args.priority
        )

        if not tests:
            print("Keine aktiven Test Cases in dieser Suite gefunden")
            return

        print(f"🚀 Running {len(tests)} tests...")

        passed = 0
        failed = 0
        errors = 0

        for test in tests:
            print(f"\n🧪 {test['name']}...", end=" ", flush=True)

            try:
                result = self.test_runner.execute_test_case(test['id'])

                if result.status == 'passed':
                    print("✅")
                    passed += 1
                elif result.status == 'failed':
                    print(f"❌ (exit {result.exit_code})")
                    failed += 1
                    if args.stop_on_fail:
                        print("\n⏸️  Stopping on failure")
                        break
                else:
                    print(f"🚨 {result.status}")
                    errors += 1
                    if args.stop_on_fail:
                        print("\n⏸️  Stopping on error")
                        break
            except Exception as e:
                print(f"🚨 {e}")
                errors += 1
                if args.stop_on_fail:
                    break

        # Summary
        print(f"\n{'='*50}")
        print(f"Results: ✅ {passed} | ❌ {failed} | 🚨 {errors}")
        success_rate = (passed / len(tests) * 100) if tests else 0
        print(f"Success Rate: {success_rate:.1f}%")

    def handle_test_history(self, args):
        """Show test execution history"""
        history = self.test_runner.get_test_history(
            test_case_id=args.test_case_id,
            limit=args.limit
        )

        if not history:
            print("Keine Execution History gefunden")
            return

        print(f"\n📊 Execution History (letzte {len(history)}):\n")
        for entry in history:
            status_icon = {"passed": "✅", "failed": "❌", "timeout": "⏱️", "error": "🚨"}.get(entry['status'], "❓")
            timestamp = datetime.fromtimestamp(entry['executed_at']).strftime('%Y-%m-%d %H:%M:%S')
            print(f"{status_icon} {timestamp} | {entry['duration_ms']}ms | Exit: {entry['exit_code']}")
            if entry['stderr_preview']:
                print(f"   stderr: {entry['stderr_preview'][:60]}...")

    def handle_test_stats(self, args):
        """Show test statistics"""
        if args.case:
            # Test case stats
            stats = self.test_reporter.get_test_case_stats(
                test_case_id=args.case,
                days=args.days
            )
            if not stats:
                print("Test Case nicht gefunden")
                return

            print(f"\n📊 Test Case Statistiken ({args.days} Tage):\n")
            print(f"Test: {stats['test_case']['name']}")
            print(f"Suite: {stats['test_case']['suite_name']}")
            print(f"\nRuns: {stats['statistics']['total_runs']}")
            print(f"Passed: {stats['statistics']['passed']}")
            print(f"Failed: {stats['statistics']['failed']}")
            print(f"Success Rate: {stats['success_rate']}%")
            if stats['statistics']['avg_duration']:
                print(f"\nDuration (ms):")
                print(f"  Avg: {stats['statistics']['avg_duration']:.0f}")
                print(f"  Min: {stats['statistics']['min_duration']}")
                print(f"  Max: {stats['statistics']['max_duration']}")

        elif args.suite:
            # Suite stats
            stats = self.test_reporter.get_suite_summary(args.suite)
            if not stats:
                print("Test Suite nicht gefunden")
                return

            print(f"\n📊 Test Suite Statistiken:\n")
            print(f"Suite: {stats['suite']['name']}")
            print(f"Projekt: {stats['suite']['project_name']}")
            print(f"\nTests:")
            print(f"  Total: {stats['test_counts']['total']}")
            print(f"  Active: {stats['test_counts']['active']}")
            print(f"  Critical: {stats['test_counts']['critical']}")
            print(f"\nExecutions:")
            print(f"  Total: {stats['execution_stats']['total_executions']}")
            print(f"  Passed: {stats['execution_stats']['passed']}")
            print(f"  Failed: {stats['execution_stats']['failed']}")
            print(f"  Success Rate: {stats['success_rate']}%")

        elif args.project:
            # Project coverage
            stats = self.test_reporter.get_project_coverage(args.project)
            print(f"\n📊 Project Coverage: {args.project}\n")
            print(f"Suites: {stats['suites']['total']} (active: {stats['suites']['active_suites']})")
            print(f"Tests: {stats['tests']['total_tests']} (critical: {stats['tests']['critical_tests']})")
            print(f"\nLast 7 days:")
            print(f"  Executions: {stats['executions_last_7_days']['total_executions']}")
            print(f"  Success Rate: {stats['success_rate_7_days']}%")
        else:
            # No parameters - show usage
            print("\n❌ Bitte Parameter angeben:")
            print("  --case <id>      Test Case Statistiken")
            print("  --suite <id>     Test Suite Statistiken")
            print("  --project <name> Project Coverage")
            print("\nBeispiel: cm test stats --project context-manager")

    def handle_test_failures(self, args):
        """Show recent test failures"""
        failures = self.test_reporter.get_recent_failures(
            project_name=args.project,
            limit=args.limit
        )

        if not failures:
            print("✅ Keine Fehler gefunden!")
            return

        print(f"\n❌ Letzte Fehler ({len(failures)}):\n")
        for failure in failures:
            timestamp = datetime.fromtimestamp(failure['executed_at']).strftime('%Y-%m-%d %H:%M:%S')
            print(f"❌ {timestamp} | {failure['project_name']}/{failure['suite_name']}")
            print(f"   Test: {failure['test_name']}")
            print(f"   Status: {failure['status']} | Exit: {failure['exit_code']}")
            if failure['stderr_preview']:
                print(f"   Error: {failure['stderr_preview'][:80]}...")
            print()

    def handle_test_flaky(self, args):
        """Identify flaky tests"""
        flaky = self.test_reporter.get_flaky_tests(
            project_name=args.project,
            min_runs=args.min_runs
        )

        if not flaky:
            print("✅ Keine flaky tests gefunden!")
            return

        print(f"\n⚠️  Potentiell Flaky Tests ({len(flaky)}):\n")
        for test in flaky:
            print(f"⚠️  {test['project_name']}/{test['suite_name']}/{test['test_name']}")
            print(f"   Runs: {test['total_runs']} | Passed: {test['passed']} | Failed: {test['failed']}")
            print(f"   Failure Rate: {test['failure_rate']*100:.1f}%")
            print()

    def handle_test_coverage(self, args):
        """Show test coverage"""
        coverage = self.test_reporter.get_project_coverage(args.project)

        print(f"\n📊 Test Coverage: {args.project}\n")
        print(f"Test Suites: {coverage['suites']['active_suites']}/{coverage['suites']['total_suites']}")
        print(f"Test Cases: {coverage['tests']['active_tests']}/{coverage['tests']['total_tests']}")
        print(f"Critical Tests: {coverage['tests']['critical_tests']}")

        if coverage['coverage_by_component']:
            print(f"\n📈 Coverage by Component:\n")
            for comp in coverage['coverage_by_component']:
                last_tested = datetime.fromtimestamp(comp['last_tested']).strftime('%Y-%m-%d') if comp['last_tested'] else 'Never'
                print(f"  {comp['component_name']}: {comp['coverage_percentage']:.1f}% ({comp['test_count']} tests)")
                print(f"    Last tested: {last_tested}")


    def handle_infra(self, args):
        """Infrastructure management handler"""
        if not args.infra_command:
            print("❌ Kein Subcommand angegeben")
            print("Verfügbare: add-host, list-hosts, show-host, edit-host, delete-host,")
            print("            add-service, list-services, edit-service, delete-service")
            return

        # Dispatch to subcommand handlers
        handlers = {
            'add-host': self._infra_add_host,
            'list-hosts': self._infra_list_hosts,
            'show-host': self._infra_show_host,
            'edit-host': self._infra_edit_host,
            'delete-host': self._infra_delete_host,
            'add-service': self._infra_add_service,
            'list-services': self._infra_list_services,
            'edit-service': self._infra_edit_service,
            'delete-service': self._infra_delete_service,
        }

        handler = handlers.get(args.infra_command)
        if handler:
            handler(args)
        else:
            print(f"❌ Unbekanntes Subcommand: {args.infra_command}")

    def _infra_add_host(self, args):
        """Add SSH host"""
        try:
            host_id = self.infrastructure.add_host(
                hostname=args.hostname,
                ip=args.ip,
                port=args.port,
                user=args.user,
                identity_file=args.identity_file,
                location=args.location,
                provider=args.provider,
                server_type=args.server_type,
                scope=args.scope,
                project_name=args.project,
                tags=args.tags,
                comment=args.comment
            )
            print(f"✅ Host '{args.hostname}' hinzugefügt (ID: {host_id})")
        except Exception as e:
            print(f"❌ Fehler: {e}")
            sys.exit(1)

    def _infra_list_hosts(self, args):
        """List SSH hosts"""
        hosts = self.infrastructure.list_hosts(
            scope=args.scope,
            location=args.location,
            project_name=args.project,
            tags=args.tags,
            minimal=args.minimal
        )

        if not hosts:
            print("📭 Keine Hosts gefunden")
            return

        print(f"\n🖥️  SSH Hosts ({len(hosts)})\n")

        if args.minimal:
            # Minimal table
            print(f"{'HOSTNAME':<20} {'LOCATION':<10} {'TYPE':<12} {'PROVIDER':<12} {'TAGS'}")
            print("=" * 80)
            for h in hosts:
                tags_str = ','.join(h.get('tags', [])) if h.get('tags') else ''
                print(f"{h['hostname']:<20} {h.get('location', ''):<10} "
                      f"{h.get('server_type', ''):<12} {h.get('provider', ''):<12} {tags_str}")
        else:
            # Full table
            for h in hosts:
                print(f"🔹 {h['hostname']}")
                if h.get('ip'):
                    print(f"   IP:       {h['ip']}:{h.get('port', 22)}")
                if h.get('user'):
                    print(f"   User:     {h['user']}")
                if h.get('location'):
                    print(f"   Location: {h['location']}")
                if h.get('provider'):
                    print(f"   Provider: {h['provider']} ({h.get('server_type', 'N/A')})")
                if h.get('scope'):
                    scope_info = h['scope']
                    if h.get('project_name'):
                        scope_info += f" ({h['project_name']})"
                    print(f"   Scope:    {scope_info}")
                if h.get('tags'):
                    print(f"   Tags:     {', '.join(h['tags'])}")
                print()

    def _infra_show_host(self, args):
        """Show host details"""
        host = self.infrastructure.show_host(args.hostname)

        if not host:
            print(f"❌ Host '{args.hostname}' nicht gefunden")
            return

        print(f"\n🖥️  Host: {host['hostname']}\n")
        print("━" * 60)
        print(f"SSH Config: ssh {host['hostname']}  (use this for SSH access)")
        print(f"\nConnection Details (informational):")
        if host.get('ip'):
            print(f"  IP:            {host['ip']}:{host.get('port', 22)}")
        if host.get('user'):
            print(f"  User:          {host['user']}")
        if host.get('identity_file'):
            print(f"  Identity:      {host['identity_file']}")

        print(f"\nInfo:")
        print(f"  Location:      {host.get('location', 'N/A')}")
        if host.get('provider'):
            print(f"  Provider:      {host['provider']}")
        if host.get('server_type'):
            print(f"  Type:          {host['server_type']}")
        print(f"  Scope:         {host['scope']}")
        if host.get('project_name'):
            print(f"  Project:       {host['project_name']}")

        if host.get('tags'):
            print(f"\nTags: {', '.join(host['tags'])}")

        if host.get('comment'):
            print(f"\nComment: {host['comment']}")

        # Services
        if host.get('services'):
            print(f"\n📦 Services ({len(host['services'])})")
            print("─" * 60)
            for svc in host['services']:
                env = f"[{svc['env']}]" if svc.get('env') else ''
                print(f"  • {svc['service_name']} {env}")
                if svc.get('app_path'):
                    print(f"    Path: {svc['app_path']}")
                if svc.get('service_type'):
                    print(f"    Type: {svc['service_type']}")
                if svc.get('deploy_method'):
                    print(f"    Deploy: {svc['deploy_method']}")
        print()

    def _infra_edit_host(self, args):
        """Edit host"""
        updated = self.infrastructure.edit_host(
            hostname=args.hostname,
            ip=args.ip,
            port=args.port,
            user=args.user,
            identity_file=args.identity_file,
            location=args.location,
            provider=args.provider,
            server_type=args.server_type,
            tags=args.tags,
            comment=args.comment
        )

        if updated:
            print(f"✅ Host '{args.hostname}' aktualisiert")
        else:
            print(f"❌ Host '{args.hostname}' nicht gefunden oder keine Änderungen")

    def _infra_delete_host(self, args):
        """Delete host"""
        success, message = self.infrastructure.delete_host(args.hostname, args.force)
        if success:
            print(f"✅ {message}")
        else:
            print(f"❌ {message}")
            sys.exit(1)

    def _infra_add_service(self, args):
        """Add service"""
        try:
            service_id = self.infrastructure.add_service(
                hostname=args.hostname,
                service_name=args.service_name,
                env=args.env,
                app_path=args.path,
                service_type=args.type,
                deploy_method=args.deploy_method,
                health_url=args.health_url,
                scope=args.scope,
                project_name=args.project,
                tags=args.tags,
                comment=args.comment
            )
            print(f"✅ Service '{args.service_name}' auf '{args.hostname}' hinzugefügt (ID: {service_id})")
        except Exception as e:
            print(f"❌ Fehler: {e}")
            sys.exit(1)

    def _infra_list_services(self, args):
        """List services"""
        services = self.infrastructure.list_services(
            hostname=args.host,
            env=args.env,
            scope=args.scope,
            project_name=args.project
        )

        if not services:
            print("📭 Keine Services gefunden")
            return

        print(f"\n📦 Services ({len(services)})\n")
        print(f"{'SERVICE':<25} {'ENV':<10} {'HOST':<20} {'PATH':<30}")
        print("=" * 100)

        for svc in services:
            env_str = svc.get('env') or ''
            path_str = svc.get('app_path') or ''
            if len(path_str) > 28:
                path_str = '...' + path_str[-25:]

            print(f"{svc['service_name']:<25} {env_str:<10} {svc['hostname']:<20} {path_str:<30}")

    def _infra_edit_service(self, args):
        """Edit service"""
        try:
            # Get the args, handling both --path and --deploy-method
            app_path = getattr(args, 'path', None)
            service_type = getattr(args, 'type', None)
            deploy_method = getattr(args, 'deploy_method', None)

            updated = self.infrastructure.edit_service(
                hostname=args.hostname,
                service_name=args.service_name,
                env=getattr(args, 'env', None),
                app_path=app_path,
                service_type=service_type,
                deploy_method=deploy_method,
                health_url=getattr(args, 'health_url', None),
                tags=getattr(args, 'tags', None),
                comment=getattr(args, 'comment', None)
            )

            if updated:
                print(f"✅ Service '{args.service_name}' auf Host '{args.hostname}' aktualisiert")
            else:
                print(f"❌ Service '{args.service_name}' auf Host '{args.hostname}' nicht gefunden oder keine Änderungen")
                sys.exit(1)
        except Exception as e:
            print(f"❌ Fehler: {e}")
            sys.exit(1)

    def _infra_delete_service(self, args):
        """Delete service"""
        success, message = self.infrastructure.delete_service(args.hostname, args.service_name)
        if success:
            print(f"✅ {message}")
        else:
            print(f"❌ {message}")
            sys.exit(1)
def dispatch_command(args, handlers: CommandHandlers):
    """
    Dispatch command to appropriate handler.

    Args:
        args: Parsed arguments
        handlers: CommandHandlers instance

    This is the main dispatcher that routes commands to handlers.
    """
    command_map = {
        'save': handlers.handle_save,
        'index': handlers.handle_index,
        'session': handlers.handle_session,
        'stats': handlers.handle_stats,
        'tool-stats': handlers.handle_tool_stats,
        'search': handlers.handle_search,
        'smart-search': handlers.handle_smart_search,
        'show': handlers.handle_show,
        'projects': handlers.handle_projects,
        'vacuum': handlers.handle_vacuum,
        'cleanup': handlers.handle_cleanup,
        'tokens': handlers.handle_tokens,
        'snippet-add': handlers.handle_snippet_add,
        'snippet-search': handlers.handle_snippet_search,
        'snippet-show': handlers.handle_snippet_show,
        'snippet-list': handlers.handle_snippet_list,
        'snippet-delete': handlers.handle_snippet_delete,
        'delete': handlers.handle_delete,
        'project-delete': handlers.handle_project_delete,
        'related': handlers.handle_related,
        'git-init': handlers.handle_git_init,
        'git-info': handlers.handle_git_info,
        'commit-info': handlers.handle_commit_info,
        'ai-prompt': handlers.handle_ai_prompt,
        'ai-instruction': handlers.handle_ai_instruction,
        'ai-instruction-update': handlers.handle_ai_instruction_update,
        'todo': handlers.handle_todo,
        'test': handlers.handle_test,
        'infra': handlers.handle_infra,
    }

    if not args.command:
        print("❌ Kein Command angegeben")
        sys.exit(1)

    handler = command_map.get(args.command)
    if not handler:
        print(f"❌ Unbekanntes Command: {args.command}")
        sys.exit(1)

    handler(args)
