"""
TODO Management System for ContextWolf
Handles TODO lifecycle: create, list, update status, bulk operations

Features:
- Priority levels (high/normal/low)
- Categories for organization
- Status tracking (open/in_progress/done/cancelled)
- Bulk operations
- Smart suggestions based on context
"""

import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from ..core.database import Database
from ..core.helpers import InputValidator, format_timestamp
from ..domain.actions import ActionManager


class TodoManager:
    """
    Manages TODO items with full lifecycle support.

    Features:
    - Create TODOs with priority and category
    - Track status changes (open → in_progress → done)
    - Bulk operations for efficiency
    - Smart features (stale detection, suggestions)
    """

    def __init__(self, db: Database):
        """Initialize with database connection"""
        self.db = db
        self.action_manager = ActionManager(db)
        self.validator = InputValidator()

    def add_todo(
        self,
        summary: str,
        content: str = None,
        priority: str = 'normal',
        category: str = None,
        due_date: str = None,
        tags: List[str] = None,
        project_name: str = None,
        depends_on: List[int] = None,
        assigned_to: str = None
    ) -> int:
        """
        Create a new TODO item.

        Args:
            summary: Short description of the TODO
            content: Detailed description (optional)
            priority: Priority level (high/normal/low)
            category: Category for grouping (e.g., bug, feature, docs)
            due_date: Due date in YYYY-MM-DD format
            tags: List of tags
            project_name: Project to associate with
            depends_on: List of TODO IDs this depends on
            assigned_to: Person/team assigned to

        Returns:
            ID of created TODO
        """
        # Validate inputs
        summary = self.validator.clean_text(summary, max_length=500)
        if not summary:
            raise ValueError("TODO summary cannot be empty")

        if priority not in ['high', 'normal', 'low']:
            raise ValueError(f"Invalid priority: {priority}")

        # Create action entry
        action_id = self.action_manager.save(
            content=content or summary,
            action_type='todo',
            project=project_name,
            summary=f"[TODO] {summary}"
        )

        # Parse due date
        due_timestamp = None
        if due_date:
            try:
                due_dt = datetime.strptime(due_date, "%Y-%m-%d")
                due_timestamp = int(due_dt.timestamp())
            except ValueError:
                raise ValueError(f"Invalid date format: {due_date}. Use YYYY-MM-DD")

        # Prepare metadata
        depends_on_str = json.dumps(depends_on) if depends_on else None
        tags_str = json.dumps(tags) if tags else None

        # Insert TODO metadata
        cursor = self.db.conn.cursor()
        cursor.execute("""
            INSERT INTO todo_metadata (
                action_id, status, priority, category,
                due_date, depends_on, assigned_to, tags
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            action_id, 'open', priority, category,
            due_timestamp, depends_on_str, assigned_to, tags_str
        ))
        self.db.conn.commit()

        return action_id

    def list_todos(
        self,
        status: str = None,
        project_name: str = None,
        priority: str = None,
        category: str = None,
        assigned_to: str = None,
        include_done: bool = False,
        limit: int = 50
    ) -> List[Dict]:
        """
        List TODO items with optional filters.

        Args:
            status: Filter by status (open/in_progress/done/cancelled)
            project_name: Filter by project
            priority: Filter by priority
            category: Filter by category
            assigned_to: Filter by assignee
            include_done: Include completed TODOs
            limit: Maximum number of results

        Returns:
            List of TODO items
        """
        query = """
            SELECT
                t.id,
                t.created_at,
                t.project,
                t.summary,
                t.status,
                t.priority,
                t.category,
                t.due_date,
                t.completed_at,
                t.reopened_count,
                t.depends_on,
                t.assigned_to,
                t.tags
            FROM v_todos t
            WHERE 1=1
        """
        params = []

        if status:
            query += " AND t.status = %s"
            params.append(status)
        elif not include_done:
            query += " AND t.status != 'done' AND t.status != 'cancelled'"

        if project_name:
            query += " AND t.project = %s"
            params.append(project_name)

        if priority:
            query += " AND t.priority = %s"
            params.append(priority)

        if category:
            query += " AND t.category = %s"
            params.append(category)

        if assigned_to:
            query += " AND t.assigned_to = %s"
            params.append(assigned_to)

        # Order by priority and due date
        query += """
            ORDER BY
                CASE t.priority
                    WHEN 'high' THEN 1
                    WHEN 'normal' THEN 2
                    WHEN 'low' THEN 3
                END,
                t.due_date ASC NULLS LAST,
                t.created_at DESC
            LIMIT %s
        """
        params.append(limit)

        cursor = self.db.conn.cursor()
        results = cursor.execute(query, params).fetchall()

        todos = []
        for row in results:
            todo = dict(row)

            # Parse JSON fields
            if todo['tags']:
                todo['tags'] = json.loads(todo['tags'])
            if todo['depends_on']:
                todo['depends_on'] = json.loads(todo['depends_on'])

            # Format timestamps
            todo['created_at'] = format_timestamp(todo['created_at'])
            if todo['due_date']:
                todo['due_date'] = format_timestamp(todo['due_date'], date_only=True)
            if todo['completed_at']:
                todo['completed_at'] = format_timestamp(todo['completed_at'])

            todos.append(todo)

        return todos

    def update_status(
        self,
        todo_id: int,
        new_status: str,
        force: bool = False
    ) -> bool:
        """
        Update TODO status with validation.

        Args:
            todo_id: ID of TODO to update
            new_status: New status (open/in_progress/done/cancelled)
            force: Skip dependency checks

        Returns:
            True if updated successfully
        """
        if new_status not in ['open', 'in_progress', 'done', 'cancelled']:
            raise ValueError(f"Invalid status: {new_status}")

        cursor = self.db.conn.cursor()

        # Get current TODO
        current = cursor.execute("""
            SELECT status, depends_on
            FROM todo_metadata
            WHERE action_id = %s
        """, (todo_id,)).fetchone()

        if not current:
            raise ValueError(f"TODO #{todo_id} not found")

        # Check dependencies if moving to done
        if new_status == 'done' and not force:
            if current['depends_on']:
                deps = json.loads(current['depends_on'])
                incomplete = cursor.execute("""
                    SELECT action_id
                    FROM todo_metadata
                    WHERE action_id IN ({})
                    AND status != 'done'
                """.format(','.join(['%s'] * len(deps))), deps).fetchall()

                if incomplete:
                    incomplete_ids = [row['action_id'] for row in incomplete]
                    raise ValueError(
                        f"Cannot complete TODO #{todo_id}. "
                        f"Dependencies not done: {incomplete_ids}"
                    )

        # Update status
        update_query = "UPDATE todo_metadata SET status = %s"
        params = [new_status]

        if new_status == 'done':
            update_query += ", completed_at = %s"
            params.append(int(datetime.now().timestamp()))
        elif new_status == 'open' and current['status'] == 'done':
            # Reopening
            update_query += ", reopened_at = %s, reopened_count = reopened_count + 1"
            params.extend([int(datetime.now().timestamp())])

        update_query += " WHERE action_id = %s"
        params.append(todo_id)

        cursor.execute(update_query, params)
        self.db.conn.commit()

        return True

    def mark_done(self, todo_ids: List[int], force: bool = False) -> Dict:
        """
        Mark one or more TODOs as done (bulk operation).

        Args:
            todo_ids: List of TODO IDs
            force: Skip dependency checks

        Returns:
            Dict with success and failed IDs
        """
        success = []
        failed = []

        for todo_id in todo_ids:
            try:
                self.update_status(todo_id, 'done', force)
                success.append(todo_id)
            except Exception as e:
                failed.append({'id': todo_id, 'error': str(e)})

        return {'success': success, 'failed': failed}

    def reopen(self, todo_ids: List[int]) -> Dict:
        """
        Reopen completed TODOs.

        Args:
            todo_ids: List of TODO IDs to reopen

        Returns:
            Dict with success and failed IDs
        """
        success = []
        failed = []

        for todo_id in todo_ids:
            try:
                self.update_status(todo_id, 'open')
                success.append(todo_id)
            except Exception as e:
                failed.append({'id': todo_id, 'error': str(e)})

        return {'success': success, 'failed': failed}

    def delete_todos(self, todo_ids: List[int]) -> int:
        """
        Delete TODOs permanently.

        Args:
            todo_ids: List of TODO IDs to delete

        Returns:
            Number of deleted TODOs
        """
        cursor = self.db.conn.cursor()

        # Delete actions (cascades to todo_metadata)
        placeholders = ','.join(['%s'] * len(todo_ids))
        cursor.execute(f"""
            DELETE FROM actions
            WHERE id IN ({placeholders})
            AND id IN (SELECT action_id FROM todo_metadata)
        """, todo_ids)

        deleted = cursor.rowcount
        self.db.conn.commit()

        return deleted

    def get_stale_todos(self, days: int = 7) -> List[Dict]:
        """
        Find TODOs that haven't been updated in X days.

        Args:
            days: Number of days to consider stale

        Returns:
            List of stale TODOs
        """
        stale_timestamp = int((datetime.now() - timedelta(days=days)).timestamp())

        cursor = self.db.conn.cursor()
        results = cursor.execute("""
            SELECT * FROM v_todos
            WHERE status = 'open'
            AND created_at < %s
            ORDER BY created_at ASC
        """, (stale_timestamp,)).fetchall()

        todos = []
        for row in results:
            todo = dict(row)
            todo['created_at'] = format_timestamp(todo['created_at'])
            todo['days_old'] = (datetime.now().timestamp() - row['created_at']) // 86400
            todos.append(todo)

        return todos

    def suggest_todos(self, project_name: str = None, limit: int = 5) -> List[Dict]:
        """
        Suggest TODOs based on recent activity and patterns.

        This analyzes recent actions and suggests relevant TODOs.

        Args:
            project_name: Project context
            limit: Number of suggestions

        Returns:
            List of suggested TODO descriptions
        """
        cursor = self.db.conn.cursor()

        suggestions = []

        # Check for recent errors/fixes without TODOs
        recent_issues = cursor.execute("""
            SELECT a.summary, ac.content
            FROM actions a
            LEFT JOIN action_content ac ON a.id = ac.action_id
            WHERE a.type_id = (SELECT id FROM action_types WHERE name = 'fix')
            AND a.id NOT IN (SELECT action_id FROM todo_metadata)
            AND a.timestamp > %s
            ORDER BY a.timestamp DESC
            LIMIT 5
        """, (int((datetime.now() - timedelta(days=7)).timestamp()),)).fetchall()

        for issue in recent_issues:
            if 'test' in issue['summary'].lower():
                suggestions.append({
                    'summary': f"Add tests for: {issue['summary']}",
                    'category': 'test',
                    'priority': 'normal'
                })

        # Check for TODOs in code comments
        code_todos = cursor.execute("""
            SELECT content FROM action_content
            WHERE content LIKE '%TODO:%' OR content LIKE '%FIXME:%'
            ORDER BY action_id DESC
            LIMIT 10
        """).fetchall()

        for code in code_todos:
            import re
            matches = re.findall(r'(?:TODO|FIXME):\s*(.+?)(?:\n|$)', code['content'])
            for match in matches[:2]:  # Limit to 2 per code block
                suggestions.append({
                    'summary': match.strip(),
                    'category': 'code',
                    'priority': 'normal'
                })

        # Deduplicate and limit
        seen = set()
        unique_suggestions = []
        for s in suggestions:
            if s['summary'] not in seen:
                seen.add(s['summary'])
                unique_suggestions.append(s)
                if len(unique_suggestions) >= limit:
                    break

        return unique_suggestions

    def get_todo_stats(self, project_name: str = None) -> Dict:
        """
        Get TODO statistics.

        Args:
            project_name: Filter by project

        Returns:
            Statistics dictionary
        """
        cursor = self.db.conn.cursor()

        base_query = """
            FROM todo_metadata t
            JOIN actions a ON t.action_id = a.id
            {where_clause}
        """

        where_clause = ""
        params = []
        if project_name:
            where_clause = "WHERE a.project_id = (SELECT id FROM projects WHERE name = %s)"
            params = [project_name]

        # Total by status
        status_stats = cursor.execute(f"""
            SELECT
                t.status,
                COUNT(*) as count
            {base_query}
            GROUP BY t.status
        """.format(where_clause=where_clause), params).fetchall()

        # Total by priority
        priority_stats = cursor.execute(f"""
            SELECT
                t.priority,
                COUNT(*) as count
            {base_query}
            GROUP BY t.priority
        """.format(where_clause=where_clause), params).fetchall()

        # Overdue TODOs
        overdue = cursor.execute(f"""
            SELECT COUNT(*) as count
            {base_query}
            AND t.status != 'done'
            AND t.due_date < %s
        """.format(where_clause=where_clause),
        params + [int(datetime.now().timestamp())]).fetchone()

        return {
            'by_status': {row['status']: row['count'] for row in status_stats},
            'by_priority': {row['priority']: row['count'] for row in priority_stats},
            'overdue': overdue['count'] if overdue else 0,
            'total': sum(row['count'] for row in status_stats)
        }