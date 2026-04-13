"""
Search Management
Handles searching actions and listing projects.

Architecture: Domain Layer (depends only on Core)
"""

import re
import json
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from ..core.database import Database


class SearchManager:
    """
    Manages search operations.

    Responsibilities:
    - Full-text search with PostgreSQL tsvector
    - Project listing with statistics
    - Date-range filtering (time-travel search)

    Dependencies:
    - Database (core layer)
    - Optional: TokenTracker for tracking search operations
    """

    def __init__(self, database: Database, token_tracker=None):
        """
        Initialize SearchManager.

        Args:
            database: Database instance
            token_tracker: Optional TokenTracker instance
        """
        self.db = database
        self.conn = database.conn
        self.token_tracker = token_tracker

    def _build_search_query(self, query: str) -> str:
        """
        Build search query with OR logic for websearch_to_tsquery.

        Default behavior: terms joined with OR.
        Explicit operators (OR, AND, NOT, "phrase") are preserved as-is.

        Examples:
            "umami analytics"          → "umami OR analytics"
            "umami OR analytics"       → "umami OR analytics" (preserved)
            "umami AND NOT tracking"   → "umami AND NOT tracking" (preserved)
        """
        query = query.strip()
        if not query:
            return query

        # Check for explicit operators - if present, pass through
        query_upper = query.upper()
        has_operators = any(
            f' {op} ' in query_upper
            for op in ['OR', 'AND', 'NOT']
        )
        has_quotes = '"' in query

        if has_operators or has_quotes:
            return query

        # Auto-OR: join terms with OR for websearch_to_tsquery
        terms = query.split()
        return ' OR '.join(terms)

    def _parse_fts_query(self, query: str) -> str:
        """
        Parse search query with intelligent boolean operator support.

        Supports both modes:
        - Auto-OR: "tarif subscription tier" → "tarif OR subscription OR tier"
        - Explicit: "tarif OR subscription" → "tarif OR subscription"
        - Mixed: "react AND (hooks OR class)" → preserved as-is

        Operators supported:
        - OR: Match any term
        - AND: Match all terms
        - NOT: Exclude term
        - NEAR(N): Terms within N words
        - "phrase": Exact phrase

        Args:
            query: User's search query

        Returns:
            Parsed query string for websearch_to_tsquery

        Examples:
            >>> _parse_fts_query("python django")
            "python OR django"
            >>> _parse_fts_query("python OR django")
            "python OR django"
            >>> _parse_fts_query("python AND NOT django")
            "python AND NOT django"
            >>> _parse_fts_query("file.py OR file.js")
            '"file.py" OR "file.js"'
        """
        query = query.strip()

        # Check if query contains boolean operators
        query_upper = query.upper()
        has_operators = any(
            f' {op} ' in query_upper or query_upper.startswith(f'{op} ') or query_upper.endswith(f' {op}')
            for op in ['OR', 'AND', 'NOT']
        )

        # Check for advanced search features
        has_near = 'NEAR' in query_upper
        has_parentheses = '(' in query or ')' in query
        has_quotes = '"' in query or "'" in query

        # If user provided explicit operators or advanced features, preserve
        if has_operators or has_near or has_parentheses or has_quotes:
            return self._quote_special_terms_preserve_operators(query)
        else:
            # Auto-OR mode: split and join with OR
            return self._auto_or_terms(query)

    def _quote_special_terms_preserve_operators(self, query: str) -> str:
        """
        Quote special characters while preserving search operators.

        Args:
            query: Query with explicit operators

        Returns:
            Query with special chars quoted, operators preserved
        """
        # Split by spaces but preserve quoted strings and operators
        parts = []
        in_quotes = False
        current = []
        quote_char = None

        i = 0
        while i < len(query):
            char = query[i]

            if char in ['"', "'"] and not in_quotes:
                in_quotes = True
                quote_char = char
                current.append(char)
            elif char == quote_char and in_quotes:
                in_quotes = False
                current.append(char)
                quote_char = None
            elif char == ' ' and not in_quotes:
                if current:
                    parts.append(''.join(current))
                    current = []
            else:
                current.append(char)

            i += 1

        if current:
            parts.append(''.join(current))

        # Process each part
        result = []
        for part in parts:
            part_upper = part.upper()

            # Keep operators as-is
            if part_upper in ['OR', 'AND', 'NOT']:
                result.append(part_upper)
            # Keep NEAR(...) as-is
            elif part_upper.startswith('NEAR('):
                result.append(part)
            # Keep quoted strings as-is
            elif part.startswith('"') or part.startswith("'"):
                result.append(part)
            # Keep parentheses as-is
            elif part in ['(', ')']:
                result.append(part)
            # Quote terms with special chars
            elif any(c in part for c in ['/', '\\', '-', '.', ':', '@']):
                result.append(f'"{part}"')
            # Regular terms
            else:
                result.append(part)

        return ' '.join(result)

    def _auto_or_terms(self, query: str) -> str:
        """
        Auto-join terms with OR operator (backwards compatible mode).

        Args:
            query: Simple search query without operators

        Returns:
            Terms joined with OR
        """
        terms = []
        for term in query.split():
            # Quote terms with special characters
            if any(c in term for c in ['/', '\\', '-', '.', ':', '@']):
                terms.append(f'"{term}"')
            else:
                terms.append(term)

        return ' OR '.join(terms)

    def search(
        self,
        query: str,
        type_filter: str = None,
        limit: int = 20,
        days_back: int = None,
        project: str = None,
        date_from: str = None,
        date_to: str = None
    ) -> List[Dict]:
        """
        Search actions using full-text search or regular SQL.

        Args:
            query: Search query (empty or "*" for all entries)
            type_filter: Filter by action type
            limit: Maximum results
            days_back: Only show entries from last N days
            project: Filter by project (default: current directory)
            date_from: Start date (YYYY-MM-DD)
            date_to: End date (YYYY-MM-DD)

        Returns:
            List of matching actions with snippets

        Features:
        - PostgreSQL full-text search with tsvector/websearch_to_tsquery
        - Date range filtering (time-travel)
        - Type filtering
        - Project filtering
        """
        cursor = self.conn.cursor()

        if not query or query.strip() == "" or query.strip() == "*":
            use_fts = False
            fts_query = None
        else:
            use_fts = True
            fts_query = self._parse_fts_query(query)

        filters = []
        params = [fts_query] if use_fts else []

        if days_back:
            cutoff_time = int(time.time()) - (days_back * 86400)
            filters.append("a.timestamp > ?")
            params.append(cutoff_time)

        if date_from:
            try:
                from_timestamp = int(datetime.strptime(date_from, "%Y-%m-%d").timestamp())
                filters.append("a.timestamp >= ?")
                params.append(from_timestamp)
            except ValueError:
                print(f"⚠️  Ungültiges Datum: {date_from} (Format: YYYY-MM-DD)")

        if date_to:
            try:
                to_timestamp = int(datetime.strptime(date_to, "%Y-%m-%d").timestamp()) + 86399
                filters.append("a.timestamp <= ?")
                params.append(to_timestamp)
            except ValueError:
                print(f"⚠️  Ungültiges Datum: {date_to} (Format: YYYY-MM-DD)")

        if project and project != "all":
            if project == "current":
                project = Path.cwd().name
            project_id = self.db.get_or_create_project(project)
            filters.append("a.project_id = ?")
            params.append(project_id)

        if type_filter:
            type_id = self.db.get_or_create_type(type_filter)
            filters.append("a.type_id = ?")
            params.append(type_id)

        where_extra = " AND " + " AND ".join(filters) if filters else ""

        if use_fts:
            # PostgreSQL with websearch_to_tsquery
            # ts_rank_cd = Cover Density Ranking: rewards proximity of matching terms
            # Normalization 1 = divides by document length (short precise matches rank higher)
            search_query = self._build_search_query(query)
            sql = f"""
                SELECT
                    a.id,
                    a.timestamp,
                    p.name as project,
                    at.name as type,
                    a.summary,
                    SUBSTRING(a.summary, 1, 100) as snippet
                FROM actions a
                JOIN projects p ON a.project_id = p.id
                JOIN action_types at ON a.type_id = at.id
                WHERE search_vector @@ websearch_to_tsquery('english', ?){where_extra}
                ORDER BY ts_rank_cd(search_vector, websearch_to_tsquery('english', ?), 1) DESC, a.timestamp DESC
                LIMIT ?
            """
            extra_params = params[1:] if params else []  # Skip fts_query
            final_params = tuple([search_query] + extra_params + [search_query, limit])
            cursor.execute(sql, final_params)
        else:
            where_clause = " WHERE " + " AND ".join(filters) if filters else ""
            sql = f"""
                SELECT
                    a.id,
                    a.timestamp,
                    p.name as project,
                    at.name as type,
                    a.summary,
                    SUBSTR(a.summary, 1, 100) as snippet
                FROM actions a
                JOIN projects p ON a.project_id = p.id
                JOIN action_types at ON a.type_id = at.id
                {where_clause}
                ORDER BY a.timestamp DESC
                LIMIT ?
            """
            cursor.execute(sql, tuple(params + [limit]))

        results = [dict(row) for row in cursor.fetchall()]

        if self.token_tracker:
            output_text = json.dumps(results)
            self.token_tracker.track_operation('search', query, output_text)

        return results

    def list_projects(self) -> List[Dict]:
        """
        List all projects with statistics.

        Returns:
            List of projects with:
            - name: Project name
            - action_count: Number of actions
            - type_count: Number of different action types
            - last_activity: Last activity timestamp
            - session_count: Number of sessions
            - total_tokens: Total tokens used

        Uses: v_project_stats view for optimized query
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM v_project_stats ORDER BY last_activity DESC")
        return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> Dict[str, Any]:
        """
        Get global statistics.

        Returns:
            Dict with:
            - projects: Number of projects
            - types: Number of action types
            - actions: Total actions
            - sessions: Total sessions
            - total_tokens: Total tokens used
            - db_size: Database size in bytes
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT
                COUNT(DISTINCT project_id) as projects,
                COUNT(DISTINCT type_id) as types,
                COUNT(id) as actions,
                COUNT(DISTINCT session_id) as sessions,
                SUM(tokens_used) as total_tokens
            FROM actions
        """)

        stats = dict(cursor.fetchone())

        # Get database size
        cursor.execute("SELECT pg_database_size(current_database()) as size")
        stats['db_size'] = cursor.fetchone()['size']

        return stats