"""
Article Research for Context Manager V4
Extracts structured experience dossiers from CM entries for blog articles.

Creates chronological timelines, type groupings, and pattern detection
from existing context entries - turning raw work logs into article material.

Architecture: Features Layer (depends on Domain + Core)
"""

import json
import logging
import re
import subprocess
import time
from datetime import datetime
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

from ..core.database import Database
from ..domain.search import SearchManager

logger = logging.getLogger("article-research")


def _strip_tags(text: str) -> str:
    """Remove HTML tags from text (no Django dependency)."""
    return re.sub(r'<[^>]+>', '', str(text))


class ArticleResearchManager:
    """
    Generates structured research dossiers from CM entries.

    Capabilities:
    - Multi-query broad search across all projects
    - Time cluster detection (entries within 24h = related work)
    - Type-based grouping (fixes, decisions, features, etc.)
    - Pattern recognition (recurring problems, lessons learned)
    - Markdown dossier rendering
    - Optional save as CM note

    Dependencies:
    - Database (core layer)
    - SearchManager (domain layer) for FTS queries
    - NotesManager (features, optional) for persisting dossiers
    """

    # Configurable limits
    TIME_CLUSTER_GAP_SECONDS = 86400  # 24h gap = new cluster
    MAX_QUERIES = 10
    MAX_RESULTS_PER_QUERY = 50
    MAX_TOTAL_ENTRIES = 80
    MAX_FTS_ENTRIES = 60  # budget for keyword search
    MAX_VECTOR_ENTRIES = 20  # reserved for semantic search
    MAX_CONTENT_PREVIEW = 500  # chars per entry in dossier
    MAX_DOSSIER_LENGTH = 100_000  # 100KB output limit
    VECTOR_SEARCH_LIMIT = 50  # candidates from vector query (filtered to MAX_VECTOR_ENTRIES)

    # Embedding worker path (separate process, separate venv)
    WORKER_DIR = Path(__file__).parent.parent.parent / "embedding_worker"
    WORKER_PYTHON = WORKER_DIR / ".venv" / "bin" / "python"
    WORKER_SCRIPT = WORKER_DIR / "worker.py"

    # Known synonyms for query expansion
    SYNONYMS = {
        'db': ['database'],
        'database': ['db'],
        'postgres': ['postgresql'],
        'postgresql': ['postgres'],
        'auth': ['authentication', 'login'],
        'authentication': ['auth'],
        'deploy': ['deployment'],
        'deployment': ['deploy'],
        'k8s': ['kubernetes'],
        'kubernetes': ['k8s'],
        'config': ['configuration'],
        'configuration': ['config'],
        'backup': ['restore', 'snapshot'],
        'docker': ['container'],
        'container': ['docker'],
        'ci': ['pipeline', 'ci/cd'],
        'pipeline': ['ci', 'ci/cd'],
        'monitoring': ['observability', 'grafana', 'prometheus'],
        'migration': ['migrate', 'upgrade'],
        'update': ['upgrade'],
        'ssl': ['tls', 'certificate'],
        'tls': ['ssl', 'certificate'],
        'dns': ['domain', 'nameserver'],
    }

    def __init__(self, db: Database, search_manager: SearchManager, notes_manager=None):
        self.db = db
        self.conn = db.conn
        self.search_manager = search_manager
        self.notes_manager = notes_manager

    def research(
        self,
        topic: str,
        queries: Optional[List[str]] = None,
        project: Optional[str] = None,
        days_back: Optional[int] = None,
        save_as_note: bool = False,
        note_project: Optional[str] = None
    ) -> str:
        """
        Research a topic and generate a structured dossier.

        Args:
            topic: Main research topic
            queries: Optional explicit search queries (auto-expanded if None)
            project: Filter by project (default: cross-project)
            days_back: Limit to last N days
            save_as_note: Persist dossier as CM note
            note_project: Project for saved note

        Returns:
            Markdown-formatted research dossier
        """
        topic = _strip_tags(topic)[:200]
        if queries:
            queries = [_strip_tags(q)[:200] for q in queries[:self.MAX_QUERIES]]

        # Step 1: Expand queries
        search_queries = queries or self._expand_queries(topic)

        # Step 2: Broad search across all queries (FTS + vector)
        entries = self._broad_search(search_queries, project, days_back, topic=topic)

        if not entries:
            return f"# Research Dossier: {topic}\n\nKeine Einträge gefunden.\n\nVerwendete Suchbegriffe: {', '.join(search_queries)}"

        # Step 3: Load full content for found entries
        self._enrich_with_content(entries)

        # Step 4: Detect time clusters
        clusters = self._detect_time_clusters(entries)

        # Step 5: Group by type
        type_groups = self._group_by_type(entries)

        # Step 6: Detect patterns
        patterns = self._detect_patterns(entries, clusters)

        # Step 7: Render dossier
        dossier = self._render_dossier(topic, search_queries, entries, clusters, type_groups, patterns)

        # Step 8: Optionally save as note
        note_id = None
        if save_as_note and self.notes_manager:
            note_id = self.notes_manager.add_note(
                title=f"Research: {topic}",
                content=dossier,
                project_name=note_project or 'context-manager',
                tags=f"research,dossier,{topic.lower().replace(' ', '-')}"
            )

        # Add save confirmation
        if note_id:
            dossier += f"\n\n---\n📝 Dossier gespeichert als Notiz #{note_id}"

        return dossier[:self.MAX_DOSSIER_LENGTH]

    def _expand_queries(self, topic: str) -> List[str]:
        """
        Generate search queries from topic via rule-based expansion.

        Returns list of queries: original topic + individual terms + synonyms.
        """
        queries = [topic]  # Full topic as primary query

        terms = topic.lower().split()

        # Add individual terms (if multi-word topic)
        if len(terms) > 1:
            for term in terms:
                if len(term) >= 3 and term not in queries:
                    queries.append(term)

        # Add synonyms
        for term in terms:
            term_lower = term.lower()
            if term_lower in self.SYNONYMS:
                for synonym in self.SYNONYMS[term_lower]:
                    if synonym not in queries:
                        queries.append(synonym)

        # Compound terms: split hyphens/underscores
        for term in terms:
            if '-' in term or '_' in term:
                parts = term.replace('_', '-').split('-')
                for part in parts:
                    if len(part) >= 3 and part not in queries:
                        queries.append(part)

        return queries[:self.MAX_QUERIES]

    def _broad_search(
        self,
        queries: List[str],
        project: Optional[str],
        days_back: Optional[int],
        topic: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute FTS + vector searches and deduplicate results.

        Hybrid approach:
        1. FTS search via SearchManager (keyword matches)
        2. Vector search via embedding worker (semantic matches)
        Merges and deduplicates by entry ID.
        """
        seen_ids: Set[int] = set()
        all_entries: List[Dict[str, Any]] = []

        search_project = project if project else 'all'

        fts_count = 0

        # Stage 1: FTS search (keyword-based, capped at MAX_FTS_ENTRIES)
        for query in queries:
            try:
                results = self.search_manager.search(
                    query=query,
                    limit=self.MAX_RESULTS_PER_QUERY,
                    project=search_project,
                    days_back=days_back
                )

                for entry in results:
                    entry_id = entry.get('id')
                    if entry_id and entry_id not in seen_ids:
                        seen_ids.add(entry_id)
                        entry['_search_source'] = 'fts'
                        all_entries.append(entry)
                        fts_count += 1

                        if fts_count >= self.MAX_FTS_ENTRIES:
                            break
            except Exception:
                continue
            if fts_count >= self.MAX_FTS_ENTRIES:
                break

        # Stage 2: Vector search (semantic, reserved budget)
        search_topic = topic or (queries[0] if queries else None)
        if search_topic:
            vector_added = 0
            try:
                vector_results = self._vector_search(
                    search_topic, search_project, days_back
                )
                for entry in vector_results:
                    entry_id = entry.get('id')
                    if entry_id and entry_id not in seen_ids:
                        seen_ids.add(entry_id)
                        entry['_search_source'] = 'vector'
                        all_entries.append(entry)
                        vector_added += 1

                        if vector_added >= self.MAX_VECTOR_ENTRIES:
                            break
            except Exception as e:
                logger.warning(f"Vector search failed (falling back to FTS only): {e}")

        return all_entries

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding vector from worker subprocess."""
        if not self.WORKER_PYTHON.exists() or not self.WORKER_SCRIPT.exists():
            return None

        try:
            result = subprocess.run(
                [str(self.WORKER_PYTHON), str(self.WORKER_SCRIPT), "embed", text],
                capture_output=True, text=True, timeout=30,
                cwd=str(self.WORKER_DIR)
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout.strip())
        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
            logger.warning(f"Embedding worker error: {e}")

        return None

    def _vector_search(
        self,
        topic: str,
        project: str,
        days_back: Optional[int]
    ) -> List[Dict[str, Any]]:
        """
        Semantic search using pgvector cosine similarity.
        Calls embedding worker for query vector, then SQL.
        """
        vector = self._get_embedding(topic)
        if not vector:
            return []

        vector_str = "[" + ",".join(f"{v:.6f}" for v in vector) + "]"

        # Build filters
        filters = []
        params = [vector_str, vector_str]  # For ORDER BY and WHERE threshold

        if days_back:
            cutoff = int(time.time()) - (days_back * 86400)
            filters.append("a.timestamp > ?")
            params.append(cutoff)

        if project and project != "all":
            from pathlib import Path as P
            proj = P.cwd().name if project == "current" else project
            project_id = self.db.get_or_create_project(proj)
            filters.append("a.project_id = ?")
            params.append(project_id)

        where_extra = " AND " + " AND ".join(filters) if filters else ""

        cursor = self.conn.cursor()
        cursor.execute(f"""
            SELECT
                a.id,
                a.timestamp,
                p.name as project,
                at.name as type,
                a.summary,
                SUBSTRING(a.summary, 1, 100) as snippet,
                1 - (a.embedding <=> ?::vector) as similarity
            FROM actions a
            JOIN projects p ON a.project_id = p.id
            JOIN action_types at ON a.type_id = at.id
            WHERE a.embedding IS NOT NULL
                AND 1 - (a.embedding <=> ?::vector) > 0.45
                {where_extra}
            ORDER BY a.embedding <=> ?::vector
            LIMIT ?
        """, tuple(params + [vector_str, self.VECTOR_SEARCH_LIMIT]))

        return [dict(row) for row in cursor.fetchall()]

    def _enrich_with_content(self, entries: List[Dict[str, Any]]) -> None:
        """
        Load full content for entries from action_content table.
        Modifies entries in-place, adding 'content' field.
        """
        if not entries:
            return

        entry_ids = [e['id'] for e in entries]

        # Batch load content
        cursor = self.conn.cursor()
        placeholders = ','.join(['?' for _ in entry_ids])

        try:
            cursor.execute(f"""
                SELECT action_id, content
                FROM action_content
                WHERE action_id IN ({placeholders})
            """, tuple(entry_ids))

            content_map = {}
            for row in cursor.fetchall():
                row_dict = dict(row) if not isinstance(row, dict) else row
                content_map[row_dict['action_id']] = row_dict['content']

            # Attach content to entries
            for entry in entries:
                entry['content'] = content_map.get(entry['id'], entry.get('summary', ''))
        except Exception:
            # Fallback: use summary as content
            for entry in entries:
                if 'content' not in entry:
                    entry['content'] = entry.get('summary', '')

    def _detect_time_clusters(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Group entries into time clusters (entries within TIME_CLUSTER_GAP_SECONDS).

        Returns list of clusters with metadata.
        """
        if not entries:
            return []

        # Sort by timestamp
        sorted_entries = sorted(entries, key=lambda e: e.get('timestamp', 0))

        clusters = []
        current_cluster = {
            'entries': [sorted_entries[0]],
            'start': sorted_entries[0].get('timestamp', 0),
            'end': sorted_entries[0].get('timestamp', 0),
        }

        for entry in sorted_entries[1:]:
            entry_ts = entry.get('timestamp', 0)
            gap = entry_ts - current_cluster['end']

            if gap <= self.TIME_CLUSTER_GAP_SECONDS:
                current_cluster['entries'].append(entry)
                current_cluster['end'] = entry_ts
            else:
                # Finalize current cluster if meaningful (2+ entries)
                if len(current_cluster['entries']) >= 2:
                    self._finalize_cluster(current_cluster)
                    clusters.append(current_cluster)

                # Start new cluster
                current_cluster = {
                    'entries': [entry],
                    'start': entry_ts,
                    'end': entry_ts,
                }

        # Don't forget last cluster
        if len(current_cluster['entries']) >= 2:
            self._finalize_cluster(current_cluster)
            clusters.append(current_cluster)

        return clusters

    def _finalize_cluster(self, cluster: Dict[str, Any]) -> None:
        """Add metadata to a finalized cluster."""
        entries = cluster['entries']

        # Collect projects and types
        projects = set()
        type_counts = defaultdict(int)
        for entry in entries:
            if entry.get('project'):
                projects.add(entry['project'])
            entry_type = entry.get('type', 'general')
            type_counts[entry_type] += 1

        cluster['projects'] = projects
        cluster['dominant_type'] = max(type_counts, key=type_counts.get) if type_counts else 'general'
        cluster['type_counts'] = dict(type_counts)
        cluster['entry_count'] = len(entries)

        # Human-readable dates
        cluster['start_date'] = self._format_timestamp(cluster['start'])
        cluster['end_date'] = self._format_timestamp(cluster['end'])

    def _group_by_type(self, entries: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group entries by semantic category."""
        groups = {
            'problems_fixes': [],     # fix
            'decisions': [],           # decision
            'features': [],            # feature, code
            'refactoring': [],         # refactor
            'infrastructure': [],      # command
            'documentation': [],       # doc, docs
            'tests': [],              # test
            'other': [],              # general, todo, etc.
        }

        type_mapping = {
            'fix': 'problems_fixes',
            'decision': 'decisions',
            'feature': 'features',
            'code': 'features',
            'refactor': 'refactoring',
            'command': 'infrastructure',
            'doc': 'documentation',
            'docs': 'documentation',
            'test': 'tests',
        }

        for entry in entries:
            entry_type = entry.get('type', 'general')
            group_key = type_mapping.get(entry_type, 'other')
            groups[group_key].append(entry)

        # Remove empty groups
        return {k: v for k, v in groups.items() if v}

    def _detect_patterns(
        self,
        entries: List[Dict[str, Any]],
        clusters: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Detect meaningful patterns in the entries.

        Patterns:
        - recurring_problem: Multiple fixes for similar issues
        - lesson_learned: Fix followed by decision within 48h
        - iterative_development: Multiple features over time
        """
        patterns = []

        # Sort entries by timestamp for pattern detection
        sorted_entries = sorted(entries, key=lambda e: e.get('timestamp', 0))

        # Pattern 1: Recurring problems (multiple fixes in same cluster)
        for cluster in clusters:
            fixes = [e for e in cluster['entries'] if e.get('type') == 'fix']
            if len(fixes) >= 2:
                patterns.append({
                    'type': 'recurring_problem',
                    'description': f"{len(fixes)} Fixes innerhalb von {cluster['start_date']} - {cluster['end_date']}",
                    'entries': fixes,
                    'projects': cluster.get('projects', set()),
                    'severity': 'high' if len(fixes) >= 3 else 'medium',
                })

        # Pattern 2: Lesson learned (fix → decision within 48h)
        fixes = [e for e in sorted_entries if e.get('type') == 'fix']
        decisions = [e for e in sorted_entries if e.get('type') == 'decision']

        for fix in fixes:
            fix_ts = fix.get('timestamp', 0)
            for decision in decisions:
                decision_ts = decision.get('timestamp', 0)
                gap = decision_ts - fix_ts
                if 0 < gap <= 172800:  # Within 48h after fix
                    patterns.append({
                        'type': 'lesson_learned',
                        'description': f"Fix → Decision",
                        'fix': fix,
                        'decision': decision,
                        'gap_hours': round(gap / 3600, 1),
                    })

        # Pattern 3: Iterative development (3+ features over time)
        features = [e for e in sorted_entries if e.get('type') in ('feature', 'code')]
        if len(features) >= 3:
            # Group by project
            project_features = defaultdict(list)
            for f in features:
                project_features[f.get('project', 'unknown')].append(f)

            for proj, proj_features in project_features.items():
                if len(proj_features) >= 3:
                    patterns.append({
                        'type': 'iterative_development',
                        'description': f"{len(proj_features)} Features in '{proj}'",
                        'entries': proj_features,
                        'project': proj,
                    })

        return patterns

    def _render_dossier(
        self,
        topic: str,
        queries: List[str],
        entries: List[Dict[str, Any]],
        clusters: List[Dict[str, Any]],
        type_groups: Dict[str, List[Dict[str, Any]]],
        patterns: List[Dict[str, Any]]
    ) -> str:
        """Render the complete research dossier as Markdown."""
        # Collect metadata
        projects = set(e.get('project', 'unknown') for e in entries)
        timestamps = [e.get('timestamp', 0) for e in entries if e.get('timestamp')]
        earliest = self._format_timestamp(min(timestamps)) if timestamps else 'N/A'
        latest = self._format_timestamp(max(timestamps)) if timestamps else 'N/A'

        lines = []

        # Header
        lines.append(f"# Research Dossier: {topic}")
        lines.append("")
        lines.append(f"**Generiert:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"**Einträge analysiert:** {len(entries)} aus {len(projects)} Projekt(en)")
        lines.append(f"**Zeitraum:** {earliest} bis {latest}")
        # Search source stats
        fts_count = sum(1 for e in entries if e.get('_search_source') == 'fts')
        vector_count = sum(1 for e in entries if e.get('_search_source') == 'vector')
        search_method = f"FTS: {fts_count}"
        if vector_count > 0:
            search_method += f", Semantisch: {vector_count}"

        lines.append(f"**Suchbegriffe:** {', '.join(queries)}")
        lines.append(f"**Suchmethode:** {search_method}")
        lines.append(f"**Projekte:** {', '.join(sorted(projects))}")
        lines.append("")

        # Executive Summary
        lines.append("---")
        lines.append("")
        lines.append("## Executive Summary")
        lines.append("")

        type_summary = []
        group_labels = {
            'problems_fixes': 'Probleme/Fixes',
            'decisions': 'Entscheidungen',
            'features': 'Features',
            'refactoring': 'Refactoring',
            'infrastructure': 'Infrastruktur',
            'documentation': 'Dokumentation',
            'tests': 'Tests',
            'other': 'Sonstiges',
        }
        for group_key, group_entries in type_groups.items():
            label = group_labels.get(group_key, group_key)
            type_summary.append(f"- **{label}:** {len(group_entries)} Einträge")
        lines.extend(type_summary)

        lines.append(f"- **Zeitcluster:** {len(clusters)} zusammenhängende Arbeitsphasen")
        lines.append(f"- **Erkannte Muster:** {len(patterns)}")
        lines.append("")

        # Patterns section (most valuable for articles)
        if patterns:
            lines.append("---")
            lines.append("")
            lines.append("## Erkannte Muster")
            lines.append("")

            recurring = [p for p in patterns if p['type'] == 'recurring_problem']
            lessons = [p for p in patterns if p['type'] == 'lesson_learned']
            iterative = [p for p in patterns if p['type'] == 'iterative_development']

            if recurring:
                lines.append("### Wiederkehrende Probleme")
                lines.append("")
                for p in recurring:
                    lines.append(f"- **{p['description']}** (Severity: {p['severity']})")
                    for entry in p['entries'][:5]:
                        lines.append(f"  - #{entry['id']} [{entry.get('project', '')}]: {self._truncate(entry.get('summary', ''), 120)}")
                lines.append("")

            if lessons:
                lines.append("### Lessons Learned")
                lines.append("")
                for p in lessons:
                    fix = p['fix']
                    decision = p['decision']
                    lines.append(f"- **Fix** #{fix['id']}: {self._truncate(fix.get('summary', ''), 100)}")
                    lines.append(f"  → **Decision** #{decision['id']} ({p['gap_hours']}h später): {self._truncate(decision.get('summary', ''), 100)}")
                lines.append("")

            if iterative:
                lines.append("### Iterative Entwicklung")
                lines.append("")
                for p in iterative:
                    lines.append(f"- **{p['description']}**")
                    for entry in p['entries'][:5]:
                        lines.append(f"  - #{entry['id']} ({self._format_timestamp(entry.get('timestamp', 0))}): {self._truncate(entry.get('summary', ''), 100)}")
                lines.append("")

        # Time clusters (chronological story)
        if clusters:
            lines.append("---")
            lines.append("")
            lines.append("## Chronologie (Zeitcluster)")
            lines.append("")

            for i, cluster in enumerate(clusters, 1):
                proj_str = ', '.join(sorted(cluster.get('projects', set())))
                lines.append(f"### Cluster {i}: {cluster['start_date']} – {cluster['end_date']}")
                lines.append(f"**Projekte:** {proj_str} | **Einträge:** {cluster['entry_count']} | **Dominant:** {cluster['dominant_type']}")
                lines.append("")

                for entry in cluster['entries'][:10]:  # Max 10 per cluster
                    entry_date = self._format_timestamp(entry.get('timestamp', 0))
                    lines.append(f"- `[{entry.get('type', '?')}]` #{entry['id']} ({entry_date}): {self._truncate(entry.get('summary', ''), 150)}")

                lines.append("")

        # Type groups
        lines.append("---")
        lines.append("")
        lines.append("## Nach Typ")
        lines.append("")

        for group_key, group_entries in type_groups.items():
            label = group_labels.get(group_key, group_key)

            # Sort by timestamp descending
            sorted_group = sorted(group_entries, key=lambda e: e.get('timestamp', 0), reverse=True)

            lines.append(f"### {label} ({len(sorted_group)})")
            lines.append("")

            for entry in sorted_group[:15]:  # Max 15 per group
                entry_date = self._format_timestamp(entry.get('timestamp', 0))
                project = entry.get('project', '')
                summary = self._truncate(entry.get('summary', ''), 150)
                lines.append(f"- #{entry['id']} ({entry_date}) [{project}]: {summary}")

            if len(sorted_group) > 15:
                lines.append(f"- ... und {len(sorted_group) - 15} weitere")
            lines.append("")

        # Entry IDs for follow-up
        lines.append("---")
        lines.append("")
        lines.append("## Rohdaten")
        lines.append("")
        lines.append(f"Alle {len(entries)} Entry-IDs für Nachverfolgung mit `context_show(entry_id=ID)`:")
        lines.append("")

        id_list = ', '.join(str(e['id']) for e in sorted(entries, key=lambda e: e.get('timestamp', 0)))
        lines.append(f"```\n{id_list}\n```")

        return '\n'.join(lines)

    @staticmethod
    def _format_timestamp(ts) -> str:
        """Format unix timestamp to readable date."""
        if not ts or ts == 0:
            return 'N/A'
        try:
            return datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d')
        except (ValueError, TypeError, OSError):
            return str(ts)

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        """Truncate text with ellipsis."""
        if not text:
            return ''
        text = text.replace('\n', ' ').strip()
        if len(text) <= max_len:
            return text
        return text[:max_len - 3] + '...'
