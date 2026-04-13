"""
Notes Management for Context Manager V4
Handles project-linked Markdown notes for session knowledge persistence.

Replaces external tools like Obsidian for storing session context,
migration plans, architecture decisions, and other structured knowledge.
"""

from datetime import datetime
from typing import List, Dict, Optional
from ..core.database import Database


class NotesManager:
    """
    Manages Markdown notes linked to projects.

    Features:
    - Create/update/delete notes with Markdown content
    - Tag-based organization
    - Full-text search across title, content, tags
    - Project association
    """

    MAX_TITLE_LENGTH = 200
    MAX_CONTENT_LENGTH = 500_000  # 500KB
    MAX_TAGS_LENGTH = 500

    def __init__(self, db: Database):
        self.db = db
        self.conn = db.conn
        self._table_ensured = False

    def _ensure_table(self):
        """Create notes table if it doesn't exist."""
        if self._table_ensured:
            return

        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id SERIAL PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                title VARCHAR(200) NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                tags TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_notes_project_id ON notes(project_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_notes_updated_at ON notes(updated_at DESC)
        """)

        self.conn.commit()
        self._table_ensured = True

    def add_note(
        self,
        title: str,
        content: str = "",
        project_name: Optional[str] = None,
        tags: Optional[str] = "",
    ) -> int:
        """
        Create a new note.

        Args:
            title: Note title (max 200 chars)
            content: Markdown content
            project_name: Project to associate with
            tags: Comma-separated tags

        Returns:
            ID of created note
        """
        self._ensure_table()

        # Validate
        title = str(title).strip()[:self.MAX_TITLE_LENGTH]
        if not title:
            raise ValueError("Note title cannot be empty")

        content = str(content)[:self.MAX_CONTENT_LENGTH] if content else ""
        tags = str(tags).strip()[:self.MAX_TAGS_LENGTH] if tags else ""

        # Resolve project
        project_id = None
        if project_name:
            project_id = self.db.get_or_create_project(project_name)

        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO notes (project_id, title, content, tags)
            VALUES (?, ?, ?, ?)
            RETURNING id
        """, (project_id, title, content, tags))
        note_id = cursor.fetchone()['id']

        self.conn.commit()
        return note_id

    def update_note(
        self,
        note_id: int,
        title: Optional[str] = None,
        content: Optional[str] = None,
        tags: Optional[str] = None,
    ) -> bool:
        """
        Update an existing note.

        Args:
            note_id: ID of note to update
            title: New title (optional)
            content: New content (optional)
            tags: New tags (optional)

        Returns:
            True if updated
        """
        self._ensure_table()

        cursor = self.conn.cursor()

        # Check exists
        existing = cursor.execute(
            "SELECT id FROM notes WHERE id = ?", (note_id,)
        ).fetchone()
        if not existing:
            raise ValueError(f"Note #{note_id} not found")

        set_parts = []
        params = []

        if title is not None:
            set_parts.append("title = ?")
            params.append(str(title).strip()[:self.MAX_TITLE_LENGTH])

        if content is not None:
            set_parts.append("content = ?")
            params.append(str(content)[:self.MAX_CONTENT_LENGTH])

        if tags is not None:
            set_parts.append("tags = ?")
            params.append(str(tags).strip()[:self.MAX_TAGS_LENGTH])

        if not set_parts:
            return False

        set_parts.append("updated_at = NOW()")

        params.append(note_id)

        cursor.execute(
            f"UPDATE notes SET {', '.join(set_parts)} WHERE id = ?",
            params
        )
        self.conn.commit()
        return True

    def get_note(self, note_id: int) -> Optional[Dict]:
        """
        Get a single note with full content.

        Args:
            note_id: Note ID

        Returns:
            Note dict or None
        """
        self._ensure_table()

        cursor = self.conn.cursor()
        row = cursor.execute("""
            SELECT n.id, n.title, n.content, n.tags,
                   p.name as project,
                   n.created_at, n.updated_at
            FROM notes n
            LEFT JOIN projects p ON n.project_id = p.id
            WHERE n.id = ?
        """, (note_id,)).fetchone()

        return dict(row) if row else None

    def search_notes(
        self,
        query: Optional[str] = None,
        project_name: Optional[str] = None,
        tags: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict]:
        """
        Search and list notes.

        Args:
            query: Search term (searches title, content, tags)
            project_name: Filter by project
            tags: Filter by tag (partial match)
            limit: Max results

        Returns:
            List of note dicts (content truncated to preview)
        """
        self._ensure_table()

        where_parts = ["1=1"]
        params = []

        if query:
            where_parts.append(
                "(n.title ILIKE ? OR n.content ILIKE ? OR n.tags ILIKE ?)"
            )
            search = f"%{query}%"
            params.extend([search, search, search])

        if project_name:
            where_parts.append("p.name = ?")
            params.append(project_name)

        if tags:
            where_parts.append("n.tags ILIKE ?")
            params.append(f"%{tags}%")

        params.append(min(limit, 100))

        cursor = self.conn.cursor()
        rows = cursor.execute(f"""
            SELECT n.id, n.title,
                   SUBSTR(n.content, 1, 200) as content_preview,
                   LENGTH(n.content) as content_length,
                   n.tags, p.name as project,
                   n.created_at, n.updated_at
            FROM notes n
            LEFT JOIN projects p ON n.project_id = p.id
            WHERE {' AND '.join(where_parts)}
            ORDER BY n.updated_at DESC
            LIMIT ?
        """, params).fetchall()

        return [dict(row) for row in rows]

    def delete_note(self, note_id: int) -> bool:
        """
        Delete a note.

        Args:
            note_id: Note ID to delete

        Returns:
            True if deleted
        """
        self._ensure_table()

        cursor = self.conn.cursor()

        existing = cursor.execute(
            "SELECT id FROM notes WHERE id = ?", (note_id,)
        ).fetchone()
        if not existing:
            raise ValueError(f"Note #{note_id} not found")

        cursor.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        self.conn.commit()
        return True
