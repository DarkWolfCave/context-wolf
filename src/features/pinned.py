"""
Pinned Items Management - Read-only access from CLI.

Pinned items are user-curated session startup references (notes, snippets,
actions, ai_instructions) that were pinned through the optional GUI
(context-wolf-ui). The CLI only reads; writes happen in the GUI.

If the pinned_items tables do not exist (CLI standalone without GUI),
all operations return an empty result - never raise.

Architecture: Features Layer (depends on Core)
"""

from typing import Dict, List, Optional
from ..core.database import Database


class PinnedManager:
    """
    Read-only CLI access to pinned items.

    Tables are owned by the GUI. This manager never creates or alters them.
    If the tables are missing (fresh CLI install without GUI overlay),
    list() returns empty and export_markdown() returns a friendly message.
    """

    TYPE_LABELS = {
        "note": ("Notes", "note_show"),
        "action": ("Actions", "context_show"),
        "snippet": ("Snippets", "snippet_show"),
        "ai_instruction": ("AI Instructions", "ai_instruction"),
    }

    def __init__(self, db: Database):
        self.db = db

    def _tables_exist(self) -> bool:
        """Check if both pinned tables exist. Returns False on any error."""
        try:
            row = self.db.fetchone("""
                SELECT
                    EXISTS (SELECT 1 FROM information_schema.tables
                            WHERE table_name = 'pinned_items') AS items,
                    EXISTS (SELECT 1 FROM information_schema.tables
                            WHERE table_name = 'pinned_item_projects') AS projects
            """)
            return bool(row and row.get("items") and row.get("projects"))
        except Exception:
            return False

    def list(self, project: Optional[str] = None) -> List[Dict]:
        """
        List pinned items, optionally filtered by project.

        Without project: all pinned items.
        With project: global items (no scope rows) + items assigned to `project`.

        Returns empty list if tables are missing. Each item contains:
          id, item_type, item_id, sort_order, label, created_at,
          scopes (list of project names), detail (dict with title + preview).
        """
        if not self._tables_exist():
            return []

        if project:
            project_row = self.db.fetchone(
                "SELECT id FROM projects WHERE name = %s", (project,)
            )
            if not project_row:
                return []
            project_id = project_row["id"]

            rows = self.db.fetchall("""
                SELECT pi.id, pi.item_type, pi.item_id, pi.sort_order,
                       pi.label, pi.created_at
                FROM pinned_items pi
                WHERE
                  NOT EXISTS (
                    SELECT 1 FROM pinned_item_projects pip
                    WHERE pip.pinned_item_id = pi.id
                  )
                  OR
                  EXISTS (
                    SELECT 1 FROM pinned_item_projects pip
                    WHERE pip.pinned_item_id = pi.id
                      AND pip.project_id = %s
                  )
                ORDER BY
                  (SELECT COUNT(*) FROM pinned_item_projects pip2
                   WHERE pip2.pinned_item_id = pi.id) ASC,
                  pi.sort_order ASC
            """, (project_id,))
        else:
            rows = self.db.fetchall("""
                SELECT pi.id, pi.item_type, pi.item_id, pi.sort_order,
                       pi.label, pi.created_at
                FROM pinned_items pi
                ORDER BY
                  (SELECT COUNT(*) FROM pinned_item_projects pip
                   WHERE pip.pinned_item_id = pi.id) ASC,
                  pi.sort_order ASC
            """)

        items = [dict(r) for r in rows]
        if not items:
            return []

        item_ids = [r["id"] for r in items]
        scopes_map = self._fetch_scopes(item_ids)

        for item in items:
            item["scopes"] = scopes_map.get(item["id"], [])
            item["detail"] = self._fetch_detail(item["item_type"], item["item_id"])

        return items

    def _fetch_scopes(self, item_ids: List[int]) -> Dict[int, List[str]]:
        """Fetch project names per pinned item id."""
        if not item_ids:
            return {}
        placeholders = ", ".join(["%s"] * len(item_ids))
        rows = self.db.fetchall(f"""
            SELECT pip.pinned_item_id, p.name
            FROM pinned_item_projects pip
            JOIN projects p ON pip.project_id = p.id
            WHERE pip.pinned_item_id IN ({placeholders})
            ORDER BY p.name ASC
        """, tuple(item_ids))

        result: Dict[int, List[str]] = {}
        for row in rows:
            result.setdefault(row["pinned_item_id"], []).append(row["name"])
        return result

    def _fetch_detail(self, item_type: str, item_id: int) -> Optional[Dict]:
        """Fetch a short title for display based on item type."""
        queries = {
            "note": "SELECT title FROM notes WHERE id = %s",
            "action": """SELECT summary AS title FROM actions WHERE id = %s""",
            "snippet": "SELECT name AS title FROM snippets WHERE id = %s",
            "ai_instruction":
                "SELECT LEFT(instruction, 120) AS title FROM ai_instructions WHERE id = %s",
        }
        query = queries.get(item_type)
        if not query:
            return None
        try:
            row = self.db.fetchone(query, (item_id,))
            return dict(row) if row else None
        except Exception:
            return None

    def export_markdown(self, project: Optional[str] = None) -> str:
        """Format pinned items as Markdown for pasting into AI prompts."""
        if not self._tables_exist():
            return (
                "# Pinned\n\n"
                "No pinned items available. The GUI (context-wolf-ui) manages\n"
                "pinned items; without it the pinned tables are not initialized.\n"
            )

        items = self.list(project=project)

        header = "# Pinned"
        if project:
            header += f" (global + {project})"

        if not items:
            return f"{header}\n\n_No items pinned yet._\n"

        lines = [header, ""]

        grouped: Dict[str, List[Dict]] = {}
        for item in items:
            grouped.setdefault(item["item_type"], []).append(item)

        for item_type, (label, cmd) in self.TYPE_LABELS.items():
            if item_type not in grouped:
                continue
            lines.append(f"## {label}")
            for item in grouped[item_type]:
                detail = item.get("detail") or {}
                title = item.get("label") or detail.get("title") or f"#{item['item_id']}"
                scopes = item.get("scopes") or []
                scope_str = f"[{', '.join(scopes)}]" if scopes else "[global]"
                lines.append(f"- `{cmd}({item['item_id']})` - {title} {scope_str}")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"
