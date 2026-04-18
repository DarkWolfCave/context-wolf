"""
AI Prompt Manager

Features Layer: Generates AI-optimized session prompts.
Architecture: Features Layer
Dependencies: Domain + Features managers
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Set
import re

from ..core.sql_utils import format_timestamp_sql


class AIPromptManager:
    """Generates AI-optimized prompts with context"""

    def __init__(self, search_manager, session_manager, snippet_manager, ai_instruction_manager, git_integration=None):
        """Initialize with manager dependencies"""
        self.search = search_manager
        self.session_mgr = session_manager
        self.snippets = snippet_manager
        self.ai_instructions = ai_instruction_manager
        self.git_integration = git_integration
        self.conn = search_manager.conn

    def generate_session_prompt(self, project: str = None, include_todos: bool = True,
                               include_snippets: bool = True, verbose: bool = False,
                               smart: bool = False, hours: int = 24) -> str:
        """
        Generate full session-start prompt

        Args:
            project: Project name (default: current directory)
            include_todos: Include open TODOs
            include_snippets: Include top snippets
            verbose: Include more details
            smart: Enable session-aware smart filtering (reduces tokens by ~8-55%)
            hours: Hours to look back for session analysis (default: 24, only for smart mode)

        Returns:
            Formatted prompt string with token count header
        """

        project = project or Path.cwd().name
        current_time = datetime.now()

        # Smart Mode: Analyze recent sessions for context
        work_context = None
        if smart:
            try:
                recent_sessions = self.session_mgr.get_recent_sessions(
                    hours=hours,  # Configurable time window (default: 24h)
                    total_actions_limit=200,
                    important_types_only=True,
                    project=project
                )
                if recent_sessions:
                    work_context = self._analyze_work_context(recent_sessions)
                    work_context['project'] = project
            except Exception as e:
                # Graceful degradation: Fall back to normal mode
                print(f"⚠️  Smart mode failed, falling back to normal: {e}", file=__import__('sys').stderr)
                smart = False

        # Collect context information
        context_parts = []

        # Header with token info (will be updated at the end)
        header_placeholder = "___HEADER_PLACEHOLDER___"
        context_parts.append(header_placeholder)

        # Last session summary
        session_info = self._get_session_summary(project)
        if session_info:
            context_parts.append(f"""
## 📅 Last session ({session_info['time']}):
{session_info['summary']}
""")

        # Current state from DB
        stats = self._get_project_stats(project)
        if stats:
            context_parts.append(f"""
## 📊 Current state:
- Entries in project: {stats['entry_count']}
- Last activity: {stats['last_activity']}
- Mainly: {', '.join(stats['top_types'])}
""")

        # Open TODOs
        if include_todos:
            todos = self._get_open_todos(project)
            if todos:
                context_parts.append(f"""
## 📝 Open TODOs:
{todos}
""")

        # Git Status
        git_info = self._get_git_status()
        if git_info:
            context_parts.append(f"""
## 🔀 Git Status:
- Branch: {git_info['branch']}
- Uncommitted: {git_info['changes']}
- Last commit: {git_info['last_commit']}
""")

        # Top Snippets
        if include_snippets:
            snippets = self._get_top_snippets(project)
            if snippets:
                context_parts.append(f"""
## 📌 Important snippets:
{snippets}
""")

        # Commands for AI
        context_parts.append(f"""
## 🎯 KEY COMMANDS for this session:

```bash
# FIRST: Fetch current context
cm session           # Shows today's activities
cm search "TODO:" --project {project}  # Open TODOs
cm stats             # Project statistics

# DURING WORK: Save EVERYTHING
cm save "What was done" --type code

# ON ISSUES: Search history
cm search "similar problem" --project {project}
cm related <ID>      # Show related solutions

# AT THE END: Document progress
cm save "✅ Milestone reached" --type milestone
```

## ⚡ AI RULES:

1. **ALWAYS use the Context Manager:**
   - On EVERY change: `cm save "what was done" --type code`
   - On issues: `cm search "error"`

2. **NEVER use interactive prompts:**
   - `cm delete <id> --force` (with --force!)
   - Don't ask y/n questions

3. **Respect Duplicate Detection:**
   - When similar entry found → that's OK, will be saved anyway
   - Use `cm related <id>` to check related entries

4. **Use Git integration:**
   - Commits are tracked automatically
   - `cm search "commit:" --date-from {(current_time - timedelta(days=7)).strftime('%Y-%m-%d')}`
""")

        # Add AI instructions (with smart filtering if enabled)
        ai_instructions = self._get_ai_instructions(project, smart=smart, context=work_context)
        if ai_instructions:
            context_parts.append(ai_instructions)

        # Verbose mode with more details
        if verbose:
            recent_entries = self._get_recent_entries(project, limit=5)
            if recent_entries:
                context_parts.append(f"""
## 📜 Last 5 entries:
{recent_entries}
""")

        # Build prompt (without header)
        prompt_body = '\n'.join(context_parts[1:])  # Skip placeholder

        # Calculate token count (rough estimate: 1 token ≈ 4 characters)
        token_count = len(prompt_body) // 4

        # Build header with token info
        mode_str = "Smart (Session-Aware)" if smart else "Normal"
        header = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Context Manager AI-Prompt
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Mode: {mode_str}
Prompt Size: {token_count} tokens (~{len(prompt_body) / 1024:.1f} KB)
"""

        # Add smart mode stats
        if smart and work_context:
            header += f"""Focus: {work_context.get('focus', 'general').title()}
Technologies: {', '.join(list(work_context.get('technologies', []))[:5])}
Actions Analyzed: {work_context.get('action_count', 0)} (last {hours}h)
"""

        header += f"""Time: {current_time.strftime('%Y-%m-%d %H:%M')}
Project: {project}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Working on {project} in {Path.cwd()}
"""

        # Replace placeholder with actual header
        final_prompt = header + prompt_body

        return final_prompt

    def _get_session_summary(self, project: str) -> dict:
        """Get last session summary"""
        cursor = self.conn.cursor()

        # Backend-specific datetime formatting
        datetime_expr = format_timestamp_sql('a.timestamp', 'localtime')

        cursor.execute(f"""
            SELECT
                MAX({datetime_expr}) as time,
                string_agg(a.summary, ' | ') as summary
            FROM actions a
            JOIN projects p ON a.project_id = p.id
            WHERE p.name = ?
                AND a.timestamp > EXTRACT(epoch FROM now())::bigint - 86400
            GROUP BY DATE(to_timestamp(a.timestamp))
            ORDER BY MAX(a.timestamp) DESC
            LIMIT 1
        """, (project,))

        row = cursor.fetchone()
        if row:
            return {
                'time': row['time'].split(' ')[0],
                'summary': row['summary'][:200] + '...' if len(row['summary']) > 200 else row['summary']
            }
        return None

    def _get_project_stats(self, project: str) -> dict:
        """Get project statistics"""
        cursor = self.conn.cursor()

        # Backend-specific datetime formatting
        datetime_expr = format_timestamp_sql('a.timestamp', 'localtime')

        # Entry count
        cursor.execute(f"""
            SELECT
                COUNT(*) as count,
                MAX({datetime_expr}) as last_activity
            FROM actions a
            JOIN projects p ON a.project_id = p.id
            WHERE p.name = ?
        """, (project,))

        stats_row = cursor.fetchone()

        # Top types
        cursor.execute("""
            SELECT at.name, COUNT(*) as count
            FROM actions a
            JOIN projects p ON a.project_id = p.id
            JOIN action_types at ON a.type_id = at.id
            WHERE p.name = ?
            GROUP BY at.name
            ORDER BY count DESC
            LIMIT 3
        """, (project,))

        top_types = [f"{row['name']}({row['count']})" for row in cursor.fetchall()]

        if stats_row and stats_row['count'] > 0:
            return {
                'entry_count': stats_row['count'],
                'last_activity': stats_row['last_activity'],
                'top_types': top_types
            }
        return None

    def _get_open_todos(self, project: str, limit: int = 5) -> str:
        """Get open TODOs"""
        results = self.search.search("TODO:", project=project, limit=limit)

        if results:
            todo_lines = []
            for i, result in enumerate(results[:limit], 1):
                # Extrahiere TODO-Text
                content = result.get('snippet', result.get('summary', ''))
                if 'TODO:' in content:
                    todo_text = content.split('TODO:')[1].split('.')[0].strip()
                    todo_lines.append(f"{i}. {todo_text[:80]}")
                elif 'TODO' in content:
                    todo_text = content.split('TODO')[1][:80].strip()
                    todo_lines.append(f"{i}. {todo_text}")

            return '\n'.join(todo_lines) if todo_lines else None
        return None

    def _get_git_status(self) -> dict:
        """Get git status if available"""
        if not self.git_integration:
            return None

        try:
            info = self.git_integration.get_git_info()
            if info:
                return {
                    'branch': info.get('branch', 'unknown'),
                    'changes': 'Yes' if info.get('has_changes') else 'No',
                    'last_commit': info.get('last_commit', 'unknown')
                }
        except Exception:
            pass
        return None

    def _get_top_snippets(self, project: str, limit: int = 3) -> str:
        """Get most-used snippets"""
        try:
            snippets = self.snippets.list_all(limit=limit)
        except Exception:
            return None
        if snippets:
            snippet_lines = []
            for s in snippets[:limit]:
                usage = f" ({s['usage_count']}x)" if s.get('usage_count', 0) > 0 else ""
                desc = (s.get('description') or '')[:50]
                snippet_lines.append(f"- {s['name']}{usage}: {desc}")
            return '\n'.join(snippet_lines)
        return None

    def _get_recent_entries(self, project: str, limit: int = 5) -> str:
        """Get recent entries for verbose mode"""
        cursor = self.conn.cursor()

        # Backend-specific datetime formatting
        datetime_expr = format_timestamp_sql('a.timestamp', 'localtime')

        cursor.execute(f"""
            SELECT
                a.id,
                at.name as type,
                a.summary,
                {datetime_expr} as time
            FROM actions a
            JOIN projects p ON a.project_id = p.id
            JOIN action_types at ON a.type_id = at.id
            WHERE p.name = ?
            ORDER BY a.timestamp DESC
            LIMIT ?
        """, (project, limit))

        entries = []
        for row in cursor.fetchall():
            entries.append(f"- #{row['id']} [{row['type']}] {row['summary'][:60]}... ({row['time']})")

        return '\n'.join(entries) if entries else None

    def _get_ai_instructions(self, project: str, smart: bool = False, context: Dict = None) -> str:
        """
        Get active AI instructions (with optional smart filtering)

        Args:
            project: Project name
            smart: Enable smart filtering based on context
            context: Work context from _analyze_work_context() (required if smart=True)

        Returns:
            Formatted string with AI instructions
        """
        # Smart Mode: Filter based on context
        if smart and context:
            instructions = self._filter_instructions_by_context(context, project)
        else:
            # Normal Mode: Get all instructions
            instructions = self.ai_instructions.get(scope='all', project=project, active_only=True)

        if not instructions:
            return None

        # Separate global and project-specific instructions
        global_instructions = [inst for inst in instructions if inst['scope'] == 'global']
        project_instructions = [inst for inst in instructions if inst['scope'] == 'project']

        # Group by priority for both categories
        def group_by_priority(inst_list):
            by_priority = {'must': [], 'should': [], 'nice': []}
            for inst in inst_list:
                priority = inst['priority']
                if priority in by_priority:
                    by_priority[priority].append(inst)
            return by_priority

        global_by_priority = group_by_priority(global_instructions)
        project_by_priority = group_by_priority(project_instructions)

        # Build output string
        output = []

        # GLOBAL INSTRUCTIONS first
        if global_instructions:
            output.append("## 🌍 GLOBAL AI INSTRUCTIONS (apply to ALL projects):\n")

            if global_by_priority['must']:
                output.append("### 🔴 MUST (Critical - ALWAYS follow):")
                for inst in global_by_priority['must']:
                    category = f"[{inst['category'].upper()}]" if inst['category'] else ""
                    output.append(f"- {category} {inst['instruction']}")
                output.append("")

            if global_by_priority['should']:
                output.append("### 🟡 SHOULD (Important - usually follow):")
                for inst in global_by_priority['should']:
                    category = f"[{inst['category'].upper()}]" if inst['category'] else ""
                    output.append(f"- {category} {inst['instruction']}")
                output.append("")

            if global_by_priority['nice']:
                output.append("### 🟢 NICE (Optional - when possible):")
                for inst in global_by_priority['nice']:
                    category = f"[{inst['category'].upper()}]" if inst['category'] else ""
                    output.append(f"- {category} {inst['instruction']}")
                output.append("")

        # PROJECT-SPECIFIC INSTRUCTIONS after
        if project_instructions:
            output.append(f"## 📁 PROJECT-SPECIFIC AI INSTRUCTIONS ({project}):\n")

            if project_by_priority['must']:
                output.append("### 🔴 MUST (Critical - ALWAYS follow):")
                for inst in project_by_priority['must']:
                    category = f"[{inst['category'].upper()}]" if inst['category'] else ""
                    output.append(f"- {category} {inst['instruction']}")
                    if inst.get('rationale'):
                        output.append(f"  → Reason: {inst['rationale']}")
                    if inst.get('examples'):
                        import json
                        try:
                            examples = json.loads(inst['examples'])
                            if examples.get('good'):
                                output.append(f"  ✅ Good: {examples['good']}")
                            if examples.get('bad'):
                                output.append(f"  ❌ Bad: {examples['bad']}")
                        except Exception:
                            pass
                output.append("")

            if project_by_priority['should']:
                output.append("### 🟡 SHOULD (Important - usually follow):")
                for inst in project_by_priority['should']:
                    category = f"[{inst['category'].upper()}]" if inst['category'] else ""
                    output.append(f"- {category} {inst['instruction']}")
                output.append("")

            if project_by_priority['nice']:
                output.append("### 🟢 NICE (Optional - when possible):")
                for inst in project_by_priority['nice']:
                    category = f"[{inst['category'].upper()}]" if inst['category'] else ""
                    output.append(f"- {category} {inst['instruction']}")
                output.append("")

        # Usage counter is updated automatically in ai_instructions.get()

        return '\n'.join(output)

    def _analyze_work_context(self, sessions: List[Dict]) -> Dict:
        """
        Analyze recent sessions to extract work context.

        Args:
            sessions: List of sessions from get_recent_sessions()

        Returns:
            Context dictionary with:
            {
                'topics': Set of keywords (>4 chars) from action content
                'technologies': Set of detected technologies
                'project': Project name
                'focus': 'development'|'infrastructure'|'documentation'|'debugging'
                'action_count': Total actions analyzed
            }

        Algorithm:
        - Extract keywords from content (words > 4 chars)
        - Detect technologies via pattern matching
        - Determine focus from action types
        - Weight: Recent actions have higher weight

        Performance: O(n) where n = number of actions (~60 typical)
        """
        context = {
            'topics': set(),
            'technologies': set(),
            'project': None,
            'focus': 'general',
            'action_count': 0
        }

        # Technology patterns to detect
        tech_patterns = {
            'docker', 'postgresql', 'postgres', 'django', 'python',
            'nfs', 'ssh', 'git', 'nginx', 'redis', 'grafana', 'loki',
            'kubernetes', 'k8s', 'typescript', 'javascript', 'react',
            'vue', 'nodejs', 'flask', 'fastapi', 'celery', 'rabbitmq',
            'mysql', 'mongodb', 'elasticsearch', 'kibana', 'prometheus'
        }

        # Action type counts for focus determination
        type_counts = {
            'development': 0,  # code, fix, feature, refactor
            'infrastructure': 0,  # docker, deploy, server
            'documentation': 0,  # doc, decision
            'debugging': 0  # fix, bug
        }

        total_actions = 0

        for session in sessions:
            for action in session.get('actions', []):
                total_actions += 1
                content = action.get('content', '').lower()
                action_type = action.get('type', '')

                # Extract keywords (words > 4 chars, alphanumeric only)
                words = re.findall(r'\b[a-z0-9]{5,}\b', content)
                # Take top frequent words (but limit to prevent noise)
                context['topics'].update(words[:10])

                # Detect technologies
                for tech in tech_patterns:
                    if tech in content:
                        context['technologies'].add(tech)

                # Determine focus from action type
                if action_type in ['code', 'feature', 'refactor']:
                    type_counts['development'] += 1
                if action_type in ['fix']:
                    type_counts['debugging'] += 1
                    type_counts['development'] += 1
                if action_type in ['doc', 'decision']:
                    type_counts['documentation'] += 1

                # Infrastructure keywords
                infra_keywords = ['docker', 'deploy', 'server', 'container', 'kubernetes', 'k8s', 'nfs', 'nginx']
                if any(kw in content for kw in infra_keywords):
                    type_counts['infrastructure'] += 1

        # Determine primary focus
        if type_counts:
            context['focus'] = max(type_counts, key=type_counts.get)

        context['action_count'] = total_actions

        # Limit topics to top 20 (most frequent/relevant)
        if len(context['topics']) > 20:
            context['topics'] = set(list(context['topics'])[:20])

        return context

    def _calculate_relevance(self, instruction: Dict, context: Dict) -> float:
        """
        Calculate relevance score for an AI instruction given current work context.

        Args:
            instruction: AI instruction dict with 'instruction', 'scope', 'priority', etc.
            context: Context dict from _analyze_work_context()

        Returns:
            Relevance score 0.0-1.0

        Algorithm:
        - Category match: 30% (category relevance to context)
        - Scope match: 30% (project > global)
        - Topic match: 20% (keywords in instruction text)
        - Technology match: 20% (tech keywords in instruction)

        Performance: O(1) - simple string operations
        """
        score = 0.0

        instruction_text = instruction.get('instruction', '').lower()
        category = (instruction.get('category') or 'general').lower()

        # Get context data
        focus = context.get('focus', 'general')
        topics = context.get('topics', set())
        technologies = context.get('technologies', set())

        # 1. Category Match (30%) - NEW!
        # Map categories to relevant keywords/contexts
        category_relevance = {
            'infrastructure': ['docker', 'deploy', 'server', 'ssh', 'nfs', 'nginx', 'container', 'kubernetes'],
            'legal': ['impressum', 'legal', 'tmg', 'ddg', 'datenschutz', 'agb', 'dsgvo'],
            'hosting': ['netcup', 'plesk', 'shared-hosting', 'cpanel', 'ftp'],
            'security': [],  # Always relevant (universal)
            'architecture': [],  # Project-specific (checked via scope)
            'mcp': [],  # Project-specific (checked via scope)
            'general': [],  # Always relevant (catch-all)
            'style': [],  # Always somewhat relevant (code style)
        }

        if category in category_relevance:
            keywords = category_relevance[category]

            # Special cases: Always relevant categories
            if category in ['security', 'general', 'style']:
                score += 0.3
            # Project-specific categories: Check if working on that project
            elif category in ['architecture', 'mcp']:
                if context.get('project') == 'context-wolf':
                    score += 0.3
                # Otherwise: 0.0 (not relevant for other projects)
            # Conditional categories: Check if context matches
            elif keywords:
                # Check if any keyword appears in context
                content_str = ' '.join(list(topics) + list(technologies) + [focus])
                if any(kw in content_str for kw in keywords):
                    score += 0.3
                # Otherwise: 0.0 (category not relevant)

        # 2. Scope Match (30%)
        if instruction['scope'] == 'project':
            if instruction.get('project') == context.get('project'):
                score += 0.3
        elif instruction['scope'] == 'global':
            score += 0.1  # Global instructions slightly relevant

        # 3. Topic Match (20%)
        # Check how many context topics appear in instruction text
        if topics:
            matches = sum(1 for topic in topics if topic in instruction_text)
            # Normalize: 3+ matches = full score
            topic_score = min(matches / 3.0, 1.0)
            score += 0.2 * topic_score

        # 4. Technology Match (20%)
        # Check how many context technologies appear in instruction text
        if technologies:
            matches = sum(1 for tech in technologies if tech in instruction_text)
            # Normalize: 2+ matches = full score
            tech_score = min(matches / 2.0, 1.0)
            score += 0.2 * tech_score

        return min(score, 1.0)

    def _filter_instructions_by_context(
        self,
        context: Dict,
        project: str
    ) -> List[Dict]:
        """
        Filter AI instructions based on context relevance.

        Args:
            context: Context dict from _analyze_work_context()
            project: Project name

        Returns:
            List of relevant AI instructions

        Filtering Rules (NEW: Category-aware filtering for "must"!):
        - 'must' priority:
            * category='general' → ALWAYS include (universal)
            * category='security' → ALWAYS include (universal)
            * Other categories → Include if relevance > 0.3 (category-aware!)
        - 'should' priority: Include if relevance > 0.4
        - 'nice' priority: Include if relevance > 0.7

        This allows filtering of categorized "must" instructions
        (e.g., Impressum only when working on legal docs),
        while keeping universal "must" instructions.

        Performance: O(n) where n = total instructions (~50)
        """
        # Get all active instructions
        all_instructions = self.ai_instructions.get(
            scope='all',
            project=project,
            active_only=True
        )

        relevant = []

        for instruction in all_instructions:
            priority = instruction.get('priority', 'nice')
            category = (instruction.get('category') or 'general').lower()

            # Calculate relevance score
            relevance = self._calculate_relevance(instruction, context)

            # Apply filtering rules based on priority AND category
            if priority == 'must':
                # Universal "must" instructions: ALWAYS include
                if category in ['general', 'security', 'style']:
                    relevant.append(instruction)
                # Category-specific "must": Filter by relevance!
                elif relevance > 0.3:
                    relevant.append(instruction)
                # Else: Even "must" can be filtered if category irrelevant

            elif priority == 'should':
                # Important instructions: Include if somewhat relevant
                if relevance > 0.4:
                    relevant.append(instruction)

            elif priority == 'nice':
                # Optional instructions: Only if highly relevant
                if relevance > 0.7:
                    relevant.append(instruction)

        return relevant

    def generate_quick_start(self, project: str = None) -> str:
        """Generate short version for quick start"""
        project = project or Path.cwd().name

        return f"""
Working on {project} in {Path.cwd()}

CURRENT STATE:
cm session  # Shows today's actions
cm search "TODO:" --project {project}  # Shows all open TODOs

START WITH THESE COMMANDS:
cm search "TODO:" --project {project}
cm search "bug" --days 7
cm stats

IMPORTANT: ALWAYS use ContextWolf for changes!
cm save "what was done" --type code
"""