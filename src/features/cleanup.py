"""
Cleanup Management - Remove orphaned and outdated indexed entries

Manages cleanup of indexed content based on file tracking metadata.
"""

from pathlib import Path
from typing import List, Dict, Any

from ..core.database import Database


class CleanupManager:
    """
    Manages cleanup of indexed entries.

    Responsibilities:
    - Find and remove orphaned entries (file deleted)
    - List legacy entries (no file tracking)
    - Show statistics about indexed content
    """

    def __init__(self, database: Database):
        """
        Initialize CleanupManager.

        Args:
            database: Database instance
        """
        self.db = database
        self.conn = database.conn

    def find_orphaned_entries(self) -> List[Dict[str, Any]]:
        """
        Find indexed entries whose source files no longer exist.

        Returns:
            List of orphaned entries with id, source_file, action_type
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT
                a.id,
                am.source_file,
                at.name as action_type,
                p.name as project
            FROM actions a
            JOIN action_metadata am ON a.id = am.action_id
            JOIN action_types at ON a.type_id = at.id
            JOIN projects p ON a.project_id = p.id
            WHERE am.source_file IS NOT NULL
        """)

        entries = cursor.fetchall()
        orphaned = []

        for action_id, source_file, action_type, project in entries:
            if source_file and not Path(source_file).exists():
                orphaned.append({
                    'id': action_id,
                    'source_file': source_file,
                    'action_type': action_type,
                    'project': project
                })

        return orphaned

    def find_legacy_entries(self) -> List[Dict[str, Any]]:
        """
        Find entries without file tracking metadata (pre-migration entries).

        Returns:
            List of legacy entries with id, summary, action_type
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT
                a.id,
                a.summary,
                at.name as action_type,
                p.name as project,
                a.timestamp
            FROM actions a
            JOIN action_types at ON a.type_id = at.id
            JOIN projects p ON a.project_id = p.id
            LEFT JOIN action_metadata am ON a.id = am.action_id
            WHERE at.name IN ('instruction', 'docs', 'reference', 'doc', 'path')
              AND (am.source_file IS NULL OR am.source_file = '')
            ORDER BY a.timestamp DESC
        """)

        entries = []
        for row in cursor.fetchall():
            entries.append({
                'id': row['id'],
                'summary': row['summary'],
                'action_type': row['action_type'],
                'project': row['project'],
                'timestamp': row['timestamp']
            })

        return entries

    def delete_entries(self, entry_ids: List[int]) -> int:
        """
        Delete entries by IDs.

        Args:
            entry_ids: List of action IDs to delete

        Returns:
            Number of entries deleted
        """
        if not entry_ids:
            return 0

        cursor = self.conn.cursor()

        placeholders = ','.join('?' * len(entry_ids))
        cursor.execute(f"""
            DELETE FROM actions
            WHERE id IN ({placeholders})
        """, entry_ids)

        deleted = cursor.rowcount
        self.conn.commit()

        return deleted

    def get_file_tracking_stats(self) -> Dict[str, Any]:
        """
        Get statistics about file tracking status.

        Returns:
            Dictionary with various statistics
        """
        cursor = self.conn.cursor()

        # Total indexed entries
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM actions a
            JOIN action_types at ON a.type_id = at.id
            WHERE at.name IN ('instruction', 'docs', 'reference', 'doc', 'path')
        """)
        total = cursor.fetchone()['count']

        # With file tracking
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM actions a
            JOIN action_types at ON a.type_id = at.id
            JOIN action_metadata am ON a.id = am.action_id
            WHERE at.name IN ('instruction', 'docs', 'reference', 'doc', 'path')
              AND am.source_file IS NOT NULL
        """)
        tracked = cursor.fetchone()['count']

        # With hash
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM actions a
            JOIN action_types at ON a.type_id = at.id
            JOIN action_metadata am ON a.id = am.action_id
            WHERE at.name IN ('instruction', 'docs', 'reference', 'doc', 'path')
              AND am.source_hash IS NOT NULL
        """)
        hashed = cursor.fetchone()['count']

        # Orphaned
        orphaned_count = len(self.find_orphaned_entries())

        # Legacy
        legacy_count = len(self.find_legacy_entries())

        return {
            'total': total,
            'tracked': tracked,
            'hashed': hashed,
            'orphaned': orphaned_count,
            'legacy': legacy_count,
            'tracked_pct': (tracked / total * 100) if total > 0 else 0,
            'hashed_pct': (hashed / total * 100) if total > 0 else 0
        }

    def find_cross_project_sessions(self) -> List[Dict[str, Any]]:
        """Identify sessions that contain actions from multiple projects."""
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT
                a.session_id,
                COUNT(*) AS action_count,
                COUNT(DISTINCT p.id) AS project_count,
                string_agg(DISTINCT p.name, ',') AS projects,
                MAX(a.timestamp) AS last_activity
            FROM actions a
            JOIN projects p ON a.project_id = p.id
            GROUP BY a.session_id
            HAVING COUNT(DISTINCT p.id) > 1
            ORDER BY last_activity DESC
        """)

        sessions = []
        for row in cursor.fetchall():
            sessions.append({
                'session_id': row['session_id'],
                'action_count': row['action_count'],
                'project_count': row['project_count'],
                'projects': row['projects'].split(',') if row['projects'] else [],
                'last_activity': row['last_activity']
            })

        return sessions

    def normalize_cross_project_sessions(self) -> int:
        """Assign unique session IDs per project to avoid cross-project clashes."""
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT session_id
            FROM actions
            GROUP BY session_id
            HAVING COUNT(DISTINCT project_id) > 1
        """)

        session_ids = [row['session_id'] for row in cursor.fetchall()]
        if not session_ids:
            return 0

        updated = 0
        for session_id in session_ids:
            cursor.execute("""
                SELECT a.id, p.name
                FROM actions a
                JOIN projects p ON a.project_id = p.id
                WHERE a.session_id = ?
            """, (session_id,))

            for row in cursor.fetchall():
                action_id = row['id']
                project_name = row['name']
                new_session_id = f"{session_id}_{project_name}"
                cursor.execute(
                    "UPDATE actions SET session_id = ? WHERE id = ?",
                    (new_session_id, action_id)
                )
                updated += 1

        self.conn.commit()
        return updated
