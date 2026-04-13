"""
Action Management - Core Business Logic
Handles saving, deleting, and managing actions.

Architecture: Domain Layer (depends only on Core, not on Features/CLI)
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any

from ..core.database import Database
from ..core.sql_utils import format_timestamp_sql
from ..core.helpers import ContentCompressor


class ActionManager:
    """
    Manages actions (save, delete, tech detection).

    Responsibilities:
    - Save new actions with content
    - Delete individual actions or entire projects
    - Auto-detect tech stack from content
    - Duplicate detection integration

    Dependencies:
    - Database (core layer)
    - ContentCompressor (core layer)
    - DuplicateDetector (lib layer - optional)
    """

    def __init__(self, database: Database, duplicate_detector=None):
        """
        Initialize ActionManager.

        Args:
            database: Database instance
            duplicate_detector: Optional DuplicateDetector instance
        """
        self.db = database
        self.conn = database.conn
        self.duplicate_detector = duplicate_detector

    def _execute(self, query, params=None):
        """Execute query with parameters"""
        return self.db.execute(query, params)

    def _fetchone(self, query, params=None):
        """Fetch one result with parameters"""
        return self.db.fetchone(query, params)

    def _fetchall(self, query, params=None):
        """Fetch all results with parameters"""
        return self.db.fetchall(query, params)

    def save(
        self,
        content: str,
        action_type: str = 'general',
        project: str = None,
        summary: str = None,
        files: List[str] = None,
        keywords: List[str] = None,
        importance: int = 5,
        metadata: str = None
    ) -> int:
        """
        Save a new action with content.

        Args:
            content: Action content
            action_type: Type of action (code, decision, fix, etc.)
            project: Project name (defaults to current directory)
            summary: Short summary (auto-generated if None)
            files: List of related files
            keywords: List of keywords
            importance: Importance level 1-10
            metadata: Additional metadata as JSON string

        Returns:
            Action ID (0 if duplicate was skipped)

        Security: Uses parameterized queries exclusively
        """
        project = project or Path.cwd().name
        project_id = self.db.get_or_create_project(project)
        type_id = self.db.get_or_create_type(action_type)
        session_id = datetime.now().strftime("%Y%m%d_%H")

        if not summary:
            summary = content[:200] + '...' if len(content) > 200 else content

        content_hash = hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()

        cursor = self.conn.cursor()

        # Check for duplicate content
        existing = self._fetchone(
            "SELECT 1 FROM action_content WHERE content_hash = ?",
            (content_hash,)
        )
        if existing:
            print(f"⏭️  Exaktes Duplikat übersprungen (gleicher Inhalt bereits gespeichert)")
            return 0

        if self.duplicate_detector:
            dup_check = self.duplicate_detector.check_for_duplicates(content, project)

            if dup_check['should_warn']:
                print(f"\n{dup_check['recommendation']}")
                if dup_check['similar_entries']:
                    print("📎 Ähnliche Einträge:")
                    for entry in dup_check['similar_entries'][:3]:
                        print(f"   #{entry['id']} [{entry['similarity']:.0%}] {entry['content'][:50]}... ({entry['time_ago']})")
                    print()

        # INSERT with RETURNING id (PostgreSQL)
        cursor.execute("""
            INSERT INTO actions (type_id, project_id, session_id, summary, importance, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            RETURNING id
        """, (type_id, project_id, session_id, summary[:500], importance, metadata))
        action_id = cursor.fetchone()['id']

        text_content, compressed_content = ContentCompressor.compress(content)
        cursor.execute("""
            INSERT INTO action_content (action_id, content, content_compressed, content_hash)
            VALUES (?, ?, ?, ?)
        """, (action_id, text_content, compressed_content, content_hash))

        if files or keywords:
            cursor.execute("""
                INSERT INTO action_metadata (action_id, files, keywords)
                VALUES (?, ?, ?)
            """, (action_id, json.dumps(files or []), json.dumps(keywords or [])))



        if self.duplicate_detector and 'dup_check' in locals():
            try:
                for entry in dup_check.get('similar_entries', [])[:3]:
                    if entry['similarity'] >= 0.7:
                        self.duplicate_detector.save_relation(
                            action_id,
                            entry['id'],
                            entry['similarity'],
                            entry['category']
                        )
            except Exception:
                pass

        self.conn.commit()

        return action_id

    def get_entry(self, entry_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a single action entry with all details.

        Args:
            entry_id: Action ID to retrieve

        Returns:
            Dictionary with entry details or None if not found
        """
        cursor = self.conn.cursor()

        datetime_expr = format_timestamp_sql('a.timestamp', 'localtime')

        cursor.execute(f"""
            SELECT
                a.id,
                a.summary,
                p.name as project,
                at.name as type,
                ac.content,
                ac.content_compressed,
                {datetime_expr} as created_at,
                a.session_id
            FROM actions a
            JOIN projects p ON a.project_id = p.id
            JOIN action_types at ON a.type_id = at.id
            LEFT JOIN action_content ac ON a.id = ac.action_id
            WHERE a.id = ?
        """, (entry_id,))

        row = cursor.fetchone()
        if not row:
            return None

        # Decompress content if available
        content = None
        if row['content_compressed']:
            content = ContentCompressor.decompress(None, row['content_compressed'])
        elif row['content']:
            content = row['content']

        return {
            'id': row['id'],
            'summary': row['summary'],
            'project': row['project'],
            'type': row['type'],
            'content': content,
            'created_at': row['created_at'],
            'session_id': row['session_id']
        }

    def move_entry(self, entry_id: int, target_project: str) -> Dict[str, Any]:
        """
        Move an action to a different project.

        Args:
            entry_id: Action ID to move
            target_project: Target project name

        Returns:
            Dict with old_project and new_project, or error key
        """
        row = self._fetchone("""
            SELECT p.name FROM actions a
            JOIN projects p ON a.project_id = p.id
            WHERE a.id = ?
        """, (entry_id,))

        if not row:
            return {"error": f"Entry #{entry_id} not found"}

        old_project = row['name']
        if old_project == target_project:
            return {"error": f"Entry #{entry_id} is already in '{target_project}'"}

        new_project_id = self.db.get_or_create_project(target_project)
        self._execute("UPDATE actions SET project_id = ? WHERE id = ?", (new_project_id, entry_id))
        self.db.commit()

        return {"old_project": old_project, "new_project": target_project}

    def delete_entry(self, entry_id: int, silent: bool = False) -> bool:
        """
        Delete a single action and all related data.

        Args:
            entry_id: Action ID to delete
            silent: If True, don't print confirmation

        Returns:
            True if deleted, False if not found

        Deletes:
        - Relations (if duplicate_detector available)
        - Metadata
        - Content
        - Action itself
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT a.summary, p.name as project, at.name as type
            FROM actions a
            JOIN projects p ON a.project_id = p.id
            JOIN action_types at ON a.type_id = at.id
            WHERE a.id = ?
        """, (entry_id,))

        entry = cursor.fetchone()
        if not entry:
            return False

        if self.duplicate_detector:
            cursor.execute(
                "DELETE FROM entry_relations WHERE source_id = ? OR target_id = ?",
                (entry_id, entry_id)
            )

        # Delete related data (explicit delete, though CASCADE would handle it)
        cursor.execute("DELETE FROM action_metadata WHERE action_id = ?", (entry_id,))
        cursor.execute("DELETE FROM action_content WHERE action_id = ?", (entry_id,))

        # Delete main action entry
        cursor.execute("DELETE FROM actions WHERE id = ?", (entry_id,))

        self.conn.commit()

        if not silent:
            print(f"🗑️  Gelöscht: #{entry_id} [{entry['type']}] {entry['summary'][:50]}...")

        return True

    def delete_project(self, project_name: str, silent: bool = False) -> Dict[str, int]:
        """
        Delete entire project with all actions, snippets, and AI instructions.

        Args:
            project_name: Name of project to delete
            silent: If True, don't print confirmation

        Returns:
            Dict with counts: {'actions': N, 'snippets': N, 'instructions': N}
            Empty dict if project not found

        Security: Uses parameterized queries with subqueries
        """
        cursor = self.conn.cursor()

        cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
        project = cursor.fetchone()
        if not project:
            return {}

        project_id = project['id']

        cursor.execute("SELECT COUNT(*) as count FROM actions WHERE project_id = ?", (project_id,))
        action_count = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM snippets WHERE project_id = ?", (project_id,))
        snippet_count = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM ai_instructions WHERE project_id = ?", (project_id,))
        instruction_count = cursor.fetchone()['count']

        if self.duplicate_detector:
            cursor.execute("""
                DELETE FROM entry_relations
                WHERE source_id IN (SELECT id FROM actions WHERE project_id = ?)
                   OR target_id IN (SELECT id FROM actions WHERE project_id = ?)
            """, (project_id, project_id))

        # Delete action-related data
        cursor.execute("""
            DELETE FROM action_metadata
            WHERE action_id IN (SELECT id FROM actions WHERE project_id = ?)
        """, (project_id,))

        cursor.execute("""
            DELETE FROM action_content
            WHERE action_id IN (SELECT id FROM actions WHERE project_id = ?)
        """, (project_id,))

        cursor.execute("DELETE FROM actions WHERE project_id = ?", (project_id,))

        # Delete snippet-related data
        cursor.execute("""
            DELETE FROM snippet_content
            WHERE snippet_id IN (SELECT id FROM snippets WHERE project_id = ?)
        """, (project_id,))

        cursor.execute("DELETE FROM snippets WHERE project_id = ?", (project_id,))

        cursor.execute("DELETE FROM ai_instructions WHERE project_id = ?", (project_id,))

        cursor.execute("DELETE FROM tech_stack WHERE project_id = ?", (project_id,))
        cursor.execute("DELETE FROM md_index WHERE project_id = ?", (project_id,))

        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))

        self.conn.commit()

        if not silent:
            print(f"🗑️  Projekt '{project_name}' gelöscht:")
            print(f"   • {action_count} Einträge entfernt")
            print(f"   • {snippet_count} Snippets entfernt")
            if instruction_count > 0:
                print(f"   • {instruction_count} AI Instructions entfernt")

        return {
            'actions': action_count,
            'snippets': snippet_count,
            'instructions': instruction_count
        }

    def get_related_entries(self, action_id: int, limit: int = 10) -> List[Dict]:
        """
        Get related/similar entries for an action.

        Args:
            action_id: Action ID
            limit: Maximum number of related entries

        Returns:
            List of related entries with similarity scores

        Requires: DuplicateDetector to be available
        """
        if not self.duplicate_detector:
            return []

        related = self.duplicate_detector.get_related_entries(action_id)
        return related[:limit] if related else []