"""
"Now" sprint backlog manager (cross-project shortlist).

Three active buckets plus a short-lived ``done`` holding area:

    today   - actively working on it now / next few hours
    week    - lined up for the next few days
    later   - acknowledged commitments, no specific date
    done    - finished; auto-purged 24h after completion

Each bucket has a WIP limit. ``add`` refuses new items when the bucket
is full, forcing a kick/demote instead of letting the list grow into
the same swamp the existing ``todo`` system already accumulates.

Items can be free-form (just a title) or reference an existing CM
entity (todo, action, note, snippet, ai_instruction, host, service).
When listed, the manager joins on the referenced table so the caller
sees live status (e.g. a referenced TODO that was meanwhile closed).

This file owns the SQL contract used by both the CLI handlers and the
MCP tools (and ultimately the GUI). The response shape produced by
:meth:`NowManager.list_items` is the public API surface - see the
``now-feature-contract`` CM note for details.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ..core.database import Database
from ..core.helpers import InputValidator


# Allowed buckets, ordered as they should appear in the UI.
BUCKETS: Tuple[str, ...] = ("today", "week", "later", "done")

# Active buckets, i.e. everything except the holding area.
ACTIVE_BUCKETS: Tuple[str, ...] = ("today", "week", "later")

# Valid linked_type values - mirrors the CHECK constraint in the migration.
LINKED_TYPES: Tuple[str, ...] = (
    "todo", "action", "note", "snippet",
    "ai_instruction", "host", "service",
)

# How long an item stays in the ``done`` bucket before lazy GC removes it.
DONE_TTL_HOURS = 24

# Hard cap that no bucket limit is allowed to exceed (mirrors the
# CHECK constraint on now_settings).
MAX_BUCKET_LIMIT = 100

DEFAULT_LIMITS: Dict[str, int] = {
    "today": 7,
    "week": 20,
    "later": 50,
}


class NowLimitExceeded(Exception):
    """Raised when adding/moving would exceed a bucket's WIP limit."""

    def __init__(self, bucket: str, limit: int, current: int):
        self.bucket = bucket
        self.limit = limit
        self.current = current
        super().__init__(
            f"Bucket '{bucket}' is full ({current}/{limit}). "
            f"Demote or remove an item before adding a new one."
        )


class NowManager:
    """Manages the cross-project "Now" sprint backlog."""

    MAX_TITLE_LENGTH = 200

    def __init__(self, db: Database):
        self.db = db
        self.conn = db.conn
        self.validator = InputValidator()

    # ------------------------------------------------------------------
    # validation helpers
    # ------------------------------------------------------------------

    def _validate_bucket(self, bucket: str) -> str:
        if bucket not in BUCKETS:
            raise ValueError(
                f"Invalid bucket '{bucket}'. Must be one of: {', '.join(BUCKETS)}"
            )
        return bucket

    def _validate_active_bucket(self, bucket: str) -> str:
        bucket = self._validate_bucket(bucket)
        if bucket == "done":
            raise ValueError(
                "Cannot add or move items directly into 'done' - use now_done()."
            )
        return bucket

    def _validate_link(
        self,
        linked_type: Optional[str],
        linked_id: Optional[int],
    ) -> Tuple[Optional[str], Optional[int]]:
        if linked_type is None and linked_id is None:
            return None, None
        if linked_type is None or linked_id is None:
            raise ValueError(
                "linked_type and linked_id must both be provided or both omitted."
            )
        if linked_type not in LINKED_TYPES:
            raise ValueError(
                f"Invalid linked_type '{linked_type}'. "
                f"Must be one of: {', '.join(LINKED_TYPES)}"
            )
        try:
            linked_id = int(linked_id)
        except (TypeError, ValueError):
            raise ValueError("linked_id must be an integer")
        if linked_id <= 0:
            raise ValueError("linked_id must be a positive integer")
        return linked_type, linked_id

    # ------------------------------------------------------------------
    # settings
    # ------------------------------------------------------------------

    def get_settings(self) -> Dict[str, int]:
        """Return the current WIP limits per active bucket."""
        cursor = self.conn.cursor()
        row = cursor.execute(
            "SELECT limit_today, limit_week, limit_later FROM now_settings WHERE id = 1"
        ).fetchone()
        if not row:
            return dict(DEFAULT_LIMITS)
        return {
            "today": row["limit_today"],
            "week": row["limit_week"],
            "later": row["limit_later"],
        }

    def update_settings(
        self,
        today: Optional[int] = None,
        week: Optional[int] = None,
        later: Optional[int] = None,
    ) -> Dict[str, int]:
        """Update one or more bucket limits. Values are clamped to [1, 100]."""
        updates: Dict[str, int] = {}
        for name, value in (("today", today), ("week", week), ("later", later)):
            if value is None:
                continue
            try:
                ivalue = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"Limit '{name}' must be an integer")
            if ivalue < 1 or ivalue > MAX_BUCKET_LIMIT:
                raise ValueError(
                    f"Limit '{name}' must be between 1 and {MAX_BUCKET_LIMIT}"
                )
            updates[name] = ivalue

        if not updates:
            return self.get_settings()

        # Ensure the singleton row exists before updating.
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO now_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING"
        )

        set_parts = []
        params: List[Any] = []
        for name, value in updates.items():
            set_parts.append(f"limit_{name} = ?")
            params.append(value)
        set_parts.append("updated_at = NOW()")

        cursor.execute(
            f"UPDATE now_settings SET {', '.join(set_parts)} WHERE id = 1",
            params,
        )
        self.conn.commit()
        return self.get_settings()

    # ------------------------------------------------------------------
    # internal: counts, positions, GC
    # ------------------------------------------------------------------

    def _count_bucket(self, bucket: str) -> int:
        cursor = self.conn.cursor()
        row = cursor.execute(
            "SELECT COUNT(*) AS c FROM now_items WHERE bucket = ?",
            (bucket,),
        ).fetchone()
        return int(row["c"]) if row else 0

    def _next_position(self, bucket: str) -> int:
        cursor = self.conn.cursor()
        row = cursor.execute(
            "SELECT COALESCE(MAX(position), -1) AS max_pos "
            "FROM now_items WHERE bucket = ?",
            (bucket,),
        ).fetchone()
        return (row["max_pos"] if row else -1) + 1

    def _gc_done(self) -> int:
        """Hard-delete `done` items older than DONE_TTL_HOURS. Returns count.

        The cutoff is computed in Python and passed as a parameter rather
        than interpolated into the SQL. Even though DONE_TTL_HOURS is a
        module constant today, treating it as data means a future refactor
        that wires it to settings or user input can't silently introduce
        a SQL-injection vector.
        """
        cutoff = datetime.now() - timedelta(hours=DONE_TTL_HOURS)
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM now_items "
            "WHERE bucket = 'done' "
            "AND done_at IS NOT NULL "
            "AND done_at < ?",
            (cutoff,),
        )
        deleted = cursor.rowcount or 0
        if deleted:
            self.conn.commit()
        return deleted

    # ------------------------------------------------------------------
    # public CRUD
    # ------------------------------------------------------------------

    def add_item(
        self,
        title: str,
        bucket: str = "today",
        project_name: Optional[str] = None,
        linked_type: Optional[str] = None,
        linked_id: Optional[int] = None,
    ) -> int:
        """Create a new Now item. Raises NowLimitExceeded when the bucket is full."""
        title = self.validator.clean_text(title, max_length=self.MAX_TITLE_LENGTH)
        # Now items are single-line by contract - collapse anything multi-
        # line so a title can't render across multiple visual rows in the UI
        # (which would also bypass the 200-char visible limit).
        title = title.replace("\n", " ").replace("\r", " ").strip()
        if not title:
            raise ValueError("Now item title cannot be empty")

        bucket = self._validate_active_bucket(bucket)
        linked_type, linked_id = self._validate_link(linked_type, linked_id)

        limits = self.get_settings()
        current = self._count_bucket(bucket)
        limit = limits[bucket]
        if current >= limit:
            raise NowLimitExceeded(bucket=bucket, limit=limit, current=current)

        project_id = None
        if project_name:
            project_id = self.db.get_or_create_project(project_name)

        position = self._next_position(bucket)

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO now_items (
                bucket, title, project_id, linked_type, linked_id, position
            ) VALUES (?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (bucket, title, project_id, linked_type, linked_id, position),
        )
        new_id = cursor.fetchone()["id"]
        self.conn.commit()
        return int(new_id)

    def move_item(self, item_id: int, to_bucket: str) -> Dict[str, Any]:
        """Move an item to another bucket. Updates moved_to_bucket_at and position."""
        to_bucket = self._validate_active_bucket(to_bucket)

        cursor = self.conn.cursor()
        row = cursor.execute(
            "SELECT bucket FROM now_items WHERE id = ?", (item_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Now item #{item_id} not found")

        old_bucket = row["bucket"]
        if old_bucket == to_bucket:
            return {"id": item_id, "bucket": to_bucket, "moved": False}

        # The target bucket's WIP limit applies even when moving an
        # existing item - otherwise users would just route around it
        # via "add somewhere else, then move".
        limits = self.get_settings()
        current = self._count_bucket(to_bucket)
        limit = limits[to_bucket]
        if current >= limit:
            raise NowLimitExceeded(bucket=to_bucket, limit=limit, current=current)

        position = self._next_position(to_bucket)
        cursor.execute(
            """
            UPDATE now_items
            SET bucket = ?,
                position = ?,
                moved_to_bucket_at = NOW(),
                done_at = NULL
            WHERE id = ?
            """,
            (to_bucket, position, item_id),
        )
        self.conn.commit()
        return {"id": item_id, "bucket": to_bucket, "moved": True, "from": old_bucket}

    def mark_done(self, item_id: int) -> bool:
        """Move an item into the `done` holding bucket."""
        cursor = self.conn.cursor()
        row = cursor.execute(
            "SELECT bucket FROM now_items WHERE id = ?", (item_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Now item #{item_id} not found")

        position = self._next_position("done")
        cursor.execute(
            """
            UPDATE now_items
            SET bucket = 'done',
                position = ?,
                done_at = NOW(),
                moved_to_bucket_at = NOW()
            WHERE id = ?
            """,
            (position, item_id),
        )
        self.conn.commit()
        return True

    def remove_item(self, item_id: int) -> bool:
        """Hard-delete an item regardless of bucket."""
        cursor = self.conn.cursor()
        existing = cursor.execute(
            "SELECT id FROM now_items WHERE id = ?", (item_id,)
        ).fetchone()
        if not existing:
            raise ValueError(f"Now item #{item_id} not found")

        cursor.execute("DELETE FROM now_items WHERE id = ?", (item_id,))
        self.conn.commit()
        return True

    def reorder_bucket(self, bucket: str, ordered_ids: List[int]) -> int:
        """Rewrite the `position` of items in a bucket from a caller-provided order."""
        bucket = self._validate_bucket(bucket)
        # bool is a subclass of int in Python, so `isinstance(True, int)` is
        # True. Exclude bools explicitly so [True, False, ...] doesn't slip
        # through as "valid ID list".
        if not isinstance(ordered_ids, list) or not all(
            isinstance(i, int) and not isinstance(i, bool) and i > 0
            for i in ordered_ids
        ):
            raise ValueError("ordered_ids must be a list of positive ints")

        cursor = self.conn.cursor()
        existing_rows = cursor.execute(
            "SELECT id FROM now_items WHERE bucket = ?", (bucket,)
        ).fetchall()
        existing_ids = {row["id"] for row in existing_rows}

        provided = set(ordered_ids)
        if provided != existing_ids:
            missing = existing_ids - provided
            extra = provided - existing_ids
            raise ValueError(
                f"ordered_ids must match the bucket's contents exactly. "
                f"Missing: {sorted(missing)}, unknown: {sorted(extra)}"
            )

        for position, item_id in enumerate(ordered_ids):
            cursor.execute(
                "UPDATE now_items SET position = ? WHERE id = ?",
                (position, item_id),
            )
        self.conn.commit()
        return len(ordered_ids)

    # ------------------------------------------------------------------
    # read paths
    # ------------------------------------------------------------------

    def get_item(self, item_id: int) -> Optional[Dict[str, Any]]:
        """Return a single Now item including JOINed linked-entity status."""
        cursor = self.conn.cursor()
        row = cursor.execute(
            """
            SELECT n.id, n.bucket, n.title,
                   p.name AS project,
                   n.linked_type, n.linked_id,
                   n.position, n.created_at, n.moved_to_bucket_at, n.done_at
            FROM now_items n
            LEFT JOIN projects p ON n.project_id = p.id
            WHERE n.id = ?
            """,
            (item_id,),
        ).fetchone()
        if not row:
            return None
        item = self._row_to_item(row)
        item["linked"] = self._resolve_link(row["linked_type"], row["linked_id"])
        return item

    def list_items(
        self,
        bucket: Optional[str] = None,
        project_name: Optional[str] = None,
        include_done: bool = False,
    ) -> Dict[str, Any]:
        """Return the public Now view.

        Returns
        -------
        dict
            ``{"items": [...], "counts": {...}, "limits": {...}}``.
            ``items`` is ordered by ``(bucket, position)`` so the UI can render
            it directly. See the ``now-feature-contract`` CM note for the
            wire-level shape (including the ``linked`` JOIN payload).
        """
        # Lazy GC: drop expired `done` rows before reading, so counts and
        # listings reflect the visible state.
        self._gc_done()

        where_parts = ["1=1"]
        params: List[Any] = []

        if bucket is not None:
            bucket = self._validate_bucket(bucket)
            where_parts.append("n.bucket = ?")
            params.append(bucket)
        elif not include_done:
            where_parts.append("n.bucket != 'done'")

        if project_name:
            where_parts.append("p.name = ?")
            params.append(project_name)

        cursor = self.conn.cursor()
        rows = cursor.execute(
            f"""
            SELECT n.id, n.bucket, n.title,
                   p.name AS project,
                   n.linked_type, n.linked_id,
                   n.position, n.created_at, n.moved_to_bucket_at, n.done_at
            FROM now_items n
            LEFT JOIN projects p ON n.project_id = p.id
            WHERE {' AND '.join(where_parts)}
            ORDER BY
                CASE n.bucket
                    WHEN 'today' THEN 1
                    WHEN 'week'  THEN 2
                    WHEN 'later' THEN 3
                    WHEN 'done'  THEN 4
                END,
                n.position ASC,
                n.id ASC
            """,
            params,
        ).fetchall()

        # Resolve link payloads in a second pass, grouped by linked_type so
        # we only run one SELECT per type even with many items.
        items: List[Dict[str, Any]] = []
        resolutions = self._resolve_links_bulk(rows)
        for row in rows:
            item = self._row_to_item(row)
            link_key = (row["linked_type"], row["linked_id"]) if row["linked_type"] else None
            item["linked"] = resolutions.get(link_key) if link_key else None
            items.append(item)

        # Counts are always returned for all buckets so the UI can render
        # capacity indicators even when filtered to a single bucket.
        count_rows = cursor.execute(
            "SELECT bucket, COUNT(*) AS c FROM now_items GROUP BY bucket"
        ).fetchall()
        counts = {b: 0 for b in BUCKETS}
        for row in count_rows:
            counts[row["bucket"]] = int(row["c"])

        return {
            "items": items,
            "counts": counts,
            "limits": self.get_settings(),
        }

    # ------------------------------------------------------------------
    # link resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_item(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": int(row["id"]),
            "bucket": row["bucket"],
            "title": row["title"],
            "project": row.get("project"),
            "position": int(row["position"]),
            "created_at": _iso(row.get("created_at")),
            "moved_to_bucket_at": _iso(row.get("moved_to_bucket_at")),
            "done_at": _iso(row.get("done_at")),
        }

    def _resolve_link(
        self,
        linked_type: Optional[str],
        linked_id: Optional[int],
    ) -> Optional[Dict[str, Any]]:
        if not linked_type or linked_id is None:
            return None
        resolutions = self._resolve_links_bulk([
            {"linked_type": linked_type, "linked_id": linked_id}
        ])
        return resolutions.get((linked_type, linked_id))

    def _resolve_links_bulk(
        self,
        rows: List[Dict[str, Any]],
    ) -> Dict[Tuple[str, int], Dict[str, Any]]:
        """Resolve all (linked_type, linked_id) tuples in a single batch.

        Returns a mapping ``{(type, id): payload}``. Missing ids are returned
        with ``exists: False`` so the UI can flag dangling references.
        """
        by_type: Dict[str, List[int]] = {}
        for row in rows:
            ltype = row.get("linked_type")
            lid = row.get("linked_id")
            if not ltype or lid is None:
                continue
            by_type.setdefault(ltype, []).append(int(lid))

        out: Dict[Tuple[str, int], Dict[str, Any]] = {}
        if not by_type:
            return out

        for ltype, ids in by_type.items():
            unique_ids = sorted(set(ids))
            found = self._fetch_linked_payload(ltype, unique_ids)
            for lid in unique_ids:
                if lid in found:
                    payload = found[lid]
                    payload.update({"type": ltype, "id": lid, "exists": True})
                    out[(ltype, lid)] = payload
                else:
                    out[(ltype, lid)] = {
                        "type": ltype,
                        "id": lid,
                        "exists": False,
                    }
        return out

    def _fetch_linked_payload(
        self,
        linked_type: str,
        ids: List[int],
    ) -> Dict[int, Dict[str, Any]]:
        """Fetch live status for one batch of (type, id_list)."""
        if not ids:
            return {}

        cursor = self.conn.cursor()
        placeholders = ",".join(["?"] * len(ids))

        try:
            if linked_type == "todo":
                rows = cursor.execute(
                    f"""
                    SELECT a.id AS id,
                           a.summary AS summary,
                           tm.status AS status,
                           tm.completed_at AS closed_at
                    FROM actions a
                    LEFT JOIN todo_metadata tm ON tm.action_id = a.id
                    WHERE a.id IN ({placeholders})
                    """,
                    ids,
                ).fetchall()
                return {
                    int(r["id"]): {
                        "summary": r.get("summary"),
                        "status": r.get("status"),
                        "closed_at": _iso_epoch(r.get("closed_at")),
                    }
                    for r in rows
                }

            if linked_type == "action":
                rows = cursor.execute(
                    f"""
                    SELECT id, summary, timestamp
                    FROM actions
                    WHERE id IN ({placeholders})
                    """,
                    ids,
                ).fetchall()
                return {
                    int(r["id"]): {
                        "summary": r.get("summary"),
                        "updated_at": _iso_epoch(r.get("timestamp")),
                    }
                    for r in rows
                }

            if linked_type == "note":
                rows = cursor.execute(
                    f"""
                    SELECT id, title, updated_at
                    FROM notes
                    WHERE id IN ({placeholders})
                    """,
                    ids,
                ).fetchall()
                return {
                    int(r["id"]): {
                        "summary": r.get("title"),
                        "updated_at": _iso(r.get("updated_at")),
                    }
                    for r in rows
                }

            if linked_type == "snippet":
                rows = cursor.execute(
                    f"""
                    SELECT id, name, description
                    FROM snippets
                    WHERE id IN ({placeholders})
                    """,
                    ids,
                ).fetchall()
                return {
                    int(r["id"]): {
                        "summary": r.get("name"),
                        "description": r.get("description"),
                    }
                    for r in rows
                }

            if linked_type == "ai_instruction":
                rows = cursor.execute(
                    f"""
                    SELECT id, instruction, updated_at
                    FROM ai_instructions
                    WHERE id IN ({placeholders})
                    """,
                    ids,
                ).fetchall()
                return {
                    int(r["id"]): {
                        "summary": (r.get("instruction") or "")[:200],
                        "updated_at": _iso_epoch(r.get("updated_at")),
                    }
                    for r in rows
                }

            if linked_type == "host":
                rows = cursor.execute(
                    f"""
                    SELECT id, hostname
                    FROM infra_hosts
                    WHERE id IN ({placeholders})
                    """,
                    ids,
                ).fetchall()
                return {
                    int(r["id"]): {"name": r.get("hostname")}
                    for r in rows
                }

            if linked_type == "service":
                rows = cursor.execute(
                    f"""
                    SELECT s.id, s.service_name, h.hostname
                    FROM infra_services s
                    LEFT JOIN infra_hosts h ON s.host_id = h.id
                    WHERE s.id IN ({placeholders})
                    """,
                    ids,
                ).fetchall()
                return {
                    int(r["id"]): {
                        "name": r.get("service_name"),
                        "hostname": r.get("hostname"),
                    }
                    for r in rows
                }
        except Exception:
            # If the referenced table doesn't exist on this install (e.g.
            # todo_metadata on a stripped-down setup), treat the link as
            # "unresolvable" rather than crashing the whole list call.
            return {}

        return {}


def _iso(ts) -> Optional[str]:
    """Render TIMESTAMP-shaped values to ISO strings; pass through plain ones."""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts.isoformat()
    return str(ts)


def _iso_epoch(ts) -> Optional[str]:
    """Render either a datetime or a Unix-epoch int to ISO."""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts.isoformat()
    try:
        return datetime.fromtimestamp(int(ts)).isoformat()
    except (TypeError, ValueError):
        return str(ts)
