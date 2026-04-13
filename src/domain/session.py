"""
Session Management
Handles session-based action grouping and retrieval.

Architecture: Domain Layer (depends only on Core)
"""

from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from ..core.database import Database


class SessionManager:
    """
    Manages sessions and session-based action queries.

    Responsibilities:
    - Retrieve actions from a session
    - Generate session IDs
    - Session-based statistics

    Session ID Format: YYYYMMDD_HH (e.g., 20250926_14)
    Groups actions by date and hour.

    Dependencies:
    - Database (core layer)
    """

    def __init__(self, database: Database):
        """
        Initialize SessionManager.

        Args:
            database: Database instance
        """
        self.db = database
        self.conn = database.conn

    def get_session(
        self,
        session_id: str = None,
        verbose: bool = False,
        project: Optional[str] = None
    ) -> List[Dict]:
        """
        Get actions from a session.

        Args:
            session_id: Session ID (format: YYYYMMDD_HH)
                       If None, uses current hour
            verbose: If True, include full content and metadata

        Returns:
            List of actions in session, ordered by timestamp DESC

        Session Format:
        - Non-verbose: type, summary, timestamp
        - Verbose: + id, content, project, metadata
        """
        if not session_id:
            session_id = datetime.now().strftime("%Y%m%d_%H")

        cursor = self.conn.cursor()

        target_project = project or Path.cwd().name

        cursor.execute(
            "SELECT id FROM projects WHERE name = ?",
            (target_project,)
        )
        project_row = cursor.fetchone()

        if not project_row:
            return []

        project_id = project_row['id']

        if verbose:
            cursor.execute("""
                SELECT
                    a.id,
                    at.name as type,
                    a.summary,
                    a.timestamp,
                    COALESCE(ac.content, '') as content,
                    p.name as project,
                    a.metadata
                FROM actions a
                JOIN action_types at ON a.type_id = at.id
                JOIN projects p ON a.project_id = p.id
                LEFT JOIN action_content ac ON a.id = ac.action_id
                WHERE a.session_id = ? AND a.project_id = ?
                ORDER BY a.timestamp DESC
            """, (session_id, project_id))
        else:
            cursor.execute("""
                SELECT
                    at.name as type,
                    a.summary,
                    a.timestamp
                FROM actions a
                JOIN action_types at ON a.type_id = at.id
                WHERE a.session_id = ? AND a.project_id = ?
                ORDER BY a.timestamp DESC
            """, (session_id, project_id))

        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def generate_session_id(timestamp: datetime = None) -> str:
        """
        Generate session ID from timestamp.

        Args:
            timestamp: Timestamp to convert (default: now)

        Returns:
            Session ID in format YYYYMMDD_HH
        """
        if not timestamp:
            timestamp = datetime.now()
        return timestamp.strftime("%Y%m%d_%H")

    def get_session_count(self, project: str = None) -> int:
        """
        Count total sessions.

        Args:
            project: Filter by project (optional)

        Returns:
            Number of unique sessions
        """
        cursor = self.conn.cursor()

        if project:
            project_id = self.db.get_or_create_project(project)
            cursor.execute("""
                SELECT COUNT(DISTINCT session_id) as count
                FROM actions
                WHERE project_id = ?
            """, (project_id,))
        else:
            cursor.execute("SELECT COUNT(DISTINCT session_id) as count FROM actions")

        return cursor.fetchone()['count']

    def get_recent_sessions(
        self,
        hours: int = 3,
        total_actions_limit: int = 200,
        important_types_only: bool = True,
        project: Optional[str] = None
    ) -> List[Dict]:
        """
        Get actions from recent sessions for context analysis.

        Args:
            hours: Number of hours to look back (default: 3)
            total_actions_limit: Maximum actions to return across all sessions (default: 200)
            important_types_only: Filter for important action types only (default: True)
            project: Filter by project (optional, defaults to current directory)

        Returns:
            List of dictionaries with session_id and actions:
            [
                {
                    'session_id': '20251029_10',
                    'actions': [
                        {'type': 'code', 'summary': '...', 'content': '...', 'timestamp': ...},
                        ...
                    ]
                },
                ...
            ]

        Important Action Types (when important_types_only=True):
        - code, fix, feature, refactor: Show WHAT is being worked on
        - decision, doc: Show WHY and context
        - Excluded: search, show, session, stats (metadata, not relevant for context)

        Performance:
        - Worst case: 200 actions × 200 chars = 40 KB
        - With type filtering: ~60 actions typical
        - Query time: ~10ms (uses idx_actions_timestamp)
        """
        cursor = self.conn.cursor()

        # Get project ID
        target_project = project or Path.cwd().name
        cursor.execute("SELECT id FROM projects WHERE name = ?", (target_project,))
        project_row = cursor.fetchone()

        if not project_row:
            return []

        project_id = project_row['id']

        # PostgreSQL time calculation
        time_threshold = f"EXTRACT(epoch FROM now())::bigint - {hours * 3600}"

        # Important action types for context analysis
        important_types = ['code', 'fix', 'feature', 'refactor', 'decision', 'doc']

        # Build WHERE clause for type filtering
        type_filter = ""
        if important_types_only:
            type_placeholders = ','.join('?' * len(important_types))
            type_filter = f"AND at.name IN ({type_placeholders})"

        # Query to get recent actions grouped by session
        # Note: We fetch actions in reverse chronological order (newest first)
        # and apply the total limit globally across all sessions
        query = f"""
            SELECT
                a.session_id,
                at.name as type,
                a.summary,
                COALESCE(ac.content, a.summary) as content,
                a.timestamp
            FROM actions a
            JOIN action_types at ON a.type_id = at.id
            LEFT JOIN action_content ac ON a.id = ac.action_id
            WHERE a.project_id = ?
                AND a.timestamp > {time_threshold}
                {type_filter}
            ORDER BY a.timestamp DESC
            LIMIT ?
        """

        # Build parameters
        params = [project_id]
        if important_types_only:
            params.extend(important_types)
        params.append(total_actions_limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # Group actions by session_id
        sessions_dict = {}
        for row in rows:
            session_id = row['session_id']
            if session_id not in sessions_dict:
                sessions_dict[session_id] = {
                    'session_id': session_id,
                    'actions': []
                }

            sessions_dict[session_id]['actions'].append({
                'type': row['type'],
                'summary': row['summary'],
                'content': row['content'],
                'timestamp': row['timestamp']
            })

        # Return sessions sorted by session_id DESC (newest first)
        return sorted(sessions_dict.values(), key=lambda x: x['session_id'], reverse=True)
