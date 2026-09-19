"""
Notes Management for ContextWolf
Handles project-linked Markdown notes for session knowledge persistence.

Replaces external tools like Obsidian for storing session context,
migration plans, architecture decisions, and other structured knowledge.
"""

import re
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

    def replace_in_note(
        self,
        note_id: int,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> Dict:
        """
        Surgically replace an exact substring in a note's content.

        This is the token-efficient alternative to update_note(content=...):
        instead of rewriting the whole note, only the matched span changes.
        String matching is exact (literal, not regex) and happens in Python;
        the write itself goes through the normal parametrized UPDATE, so there
        is no SQL-injection surface.

        Safety rules (mirroring an exact-match code editor):
        - old_string must be non-empty and differ from new_string
        - 0 matches            -> ValueError (nothing to change)
        - >1 matches & not replace_all -> ValueError (ambiguous; add context)
        - result exceeding MAX_CONTENT_LENGTH -> ValueError (no silent truncation)

        Args:
            note_id: ID of note to edit
            old_string: exact literal text to find (include surrounding
                context to make it unique)
            new_string: replacement text (may be empty to delete the span)
            replace_all: replace every occurrence instead of requiring
                exactly one

        Returns:
            Dict with {'replaced', 'old_length', 'content_length'}

        Raises:
            ValueError on any of the safety rules above or unknown note.
        """
        self._ensure_table()

        note = self.get_note(note_id)
        if not note:
            raise ValueError(f"Note #{note_id} not found")

        old_string = str(old_string)
        new_string = str(new_string)

        if old_string == "":
            raise ValueError("old_string cannot be empty")
        if old_string == new_string:
            raise ValueError("old_string and new_string are identical - nothing to change")

        content = note["content"] or ""
        count = content.count(old_string)

        if count == 0:
            raise ValueError(
                "old_string not found in note. Check whitespace/casing, or use "
                "note_grep to locate the exact text."
            )
        if count > 1 and not replace_all:
            raise ValueError(
                f"old_string is not unique ({count} matches). Add surrounding "
                f"context to target a single occurrence, or set replace_all=True."
            )

        if replace_all:
            new_content = content.replace(old_string, new_string)
            replaced = count
        else:
            new_content = content.replace(old_string, new_string, 1)
            replaced = 1

        if len(new_content) > self.MAX_CONTENT_LENGTH:
            raise ValueError(
                f"Resulting content would be {len(new_content)} chars, exceeding "
                f"the {self.MAX_CONTENT_LENGTH} char limit. Edit refused (no truncation)."
            )

        self.update_note(note_id=note_id, content=new_content)
        return {
            "replaced": replaced,
            "old_length": len(old_string),
            "content_length": len(new_content),
        }

    def grep_note(
        self,
        note_id: int,
        pattern: str,
        context: int = 2,
        ignore_case: bool = True,
        max_matches: int = 50,
    ) -> Dict:
        """
        Search within a single note and return only matching lines plus
        surrounding context, with 1-based line numbers.

        This lets a caller locate the exact text to feed into replace_in_note
        WITHOUT pulling the whole (possibly huge) note into context. Overlapping
        context windows are merged into contiguous blocks.

        Args:
            note_id: note to search
            pattern: regular expression (re.search semantics, per line)
            context: number of lines of context around each match
            ignore_case: case-insensitive matching (default True)
            max_matches: cap on matched lines; extras are reported, not silently
                dropped

        Returns:
            Dict with keys:
              'total_lines'  - line count of the note
              'match_count'  - number of matching lines found (pre-cap)
              'truncated'    - True if match_count exceeded max_matches
              'blocks'       - list of {'lines': [{'n', 'text', 'is_match'}]}

        Raises:
            ValueError on unknown note or invalid regex.
        """
        self._ensure_table()

        note = self.get_note(note_id)
        if not note:
            raise ValueError(f"Note #{note_id} not found")

        try:
            rx = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
        except re.error as exc:
            raise ValueError(f"Invalid regex pattern: {exc}")

        lines = (note["content"] or "").split("\n")
        total = len(lines)
        context = max(0, int(context))

        match_idx = [i for i, line in enumerate(lines) if rx.search(line)]
        match_count = len(match_idx)
        truncated = match_count > max_matches
        used = match_idx[:max_matches]

        # Build merged, sorted line ranges (0-based, inclusive) around matches.
        ranges: List[List[int]] = []
        for i in used:
            lo, hi = max(0, i - context), min(total - 1, i + context)
            if ranges and lo <= ranges[-1][1] + 1:
                ranges[-1][1] = max(ranges[-1][1], hi)
            else:
                ranges.append([lo, hi])

        match_set = set(used)
        blocks = []
        for lo, hi in ranges:
            block_lines = [
                {"n": j + 1, "text": lines[j], "is_match": j in match_set}
                for j in range(lo, hi + 1)
            ]
            blocks.append({"lines": block_lines})

        return {
            "total_lines": total,
            "match_count": match_count,
            "truncated": truncated,
            "blocks": blocks,
        }

    def get_note_slice(
        self,
        note_id: int,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> Optional[Dict]:
        """
        Return a note plus a line-range slice of its content (1-based,
        inclusive), for reading part of a large note without loading it whole.

        Args:
            note_id: note to read
            start_line: first line (1-based, default 1)
            end_line: last line inclusive (default: last line)

        Returns:
            Note dict (as get_note) augmented with 'content' replaced by the
            slice, plus 'slice_start', 'slice_end', 'total_lines'. None if the
            note does not exist.

        Raises:
            ValueError if the range is invalid.
        """
        note = self.get_note(note_id)
        if not note:
            return None

        lines = (note["content"] or "").split("\n")
        total = len(lines)

        start = 1 if start_line is None else int(start_line)
        end = total if end_line is None else int(end_line)

        if start < 1:
            raise ValueError("start_line must be >= 1")
        if end < start:
            raise ValueError(f"end_line ({end}) must be >= start_line ({start})")

        start = min(start, total)
        end = min(end, total)
        note["content"] = "\n".join(lines[start - 1:end])
        note["slice_start"] = start
        note["slice_end"] = end
        note["total_lines"] = total
        return note

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
