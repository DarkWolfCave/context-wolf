"""
AI Instructions Management
Handles AI coding rules and instructions for Claude Code.

Architecture: Features Layer (depends on Core)
"""

import json
from pathlib import Path
from typing import List, Dict, Optional

from ..core.database import Database
from ..core.sql_utils import format_timestamp_sql


class AIInstructionManager:
    """
    Manages AI instructions and coding rules.

    Responsibilities:
    - Save instructions with scope (global/project/session)
    - Query instructions by priority/category
    - Search instructions with full-text search
    - Toggle active/inactive status
    - Update instruction metadata

    Scope Levels:
    - global: Applies to all projects
    - project: Applies only to specific project
    - session: Applies only to current session

    Priority Levels:
    - must: Critical rules (e.g., security)
    - should: Best practices
    - nice: Optional preferences

    Dependencies:
    - Database (core layer)
    """

    VALID_SCOPES = frozenset(['global', 'project', 'session'])
    VALID_PRIORITIES = frozenset(['must', 'should', 'nice'])

    def __init__(self, database: Database):
        """
        Initialize AIInstructionManager.

        Args:
            database: Database instance
        """
        self.db = database
        self.conn = database.conn

    def save(
        self,
        instruction: str,
        scope: str = 'project',
        priority: str = 'should',
        category: str = None,
        examples: Dict = None,
        rationale: str = None,
        project: str = None,
        metadata: Dict = None
    ) -> int:
        """
        Save a new AI instruction.

        Args:
            instruction: The instruction text
            scope: global/project/session
            priority: must/should/nice
            category: Category (security, style, performance, etc.)
            examples: Dict with good/bad code examples
            rationale: Why this rule is important
            project: Project name (for project scope)
            metadata: Additional metadata

        Returns:
            Instruction ID

        Security: Checks for duplicates before inserting
        """
        project_id = None
        if scope == 'project':
            project_name = project or Path.cwd().name
            project_id = self.db.get_or_create_project(project_name)

        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT id, instruction FROM ai_instructions
            WHERE instruction = ? AND scope = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))
        """, (instruction, scope, project_id, project_id))

        existing = cursor.fetchone()
        if existing:
            print(f"⚠️  Instruction already exists (ID: {existing['id']})")
            return existing['id']

        try:
            cursor.execute("""
                INSERT INTO ai_instructions
                (instruction, scope, priority, category, examples, rationale, project_id, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                instruction,
                scope,
                priority,
                category,
                json.dumps(examples) if examples else None,
                rationale,
                project_id,
                json.dumps(metadata) if metadata else None
            ))

            # Get inserted ID via re-query (PostgreSQL RETURNING handled by trigger)
            cursor.execute("""
                SELECT id FROM ai_instructions
                WHERE instruction = ? AND scope = ?
                ORDER BY created_at DESC LIMIT 1
            """, (instruction, scope))
            instruction_id = cursor.fetchone()['id']

            self.conn.commit()
            return instruction_id
        except Exception:
            self.conn.rollback()
            raise

    def get_by_id(self, instruction_id: int) -> Optional[Dict]:
        """Return a single instruction by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM ai_instructions WHERE id = ?", (instruction_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get(
        self,
        scope: str = None,
        category: str = None,
        priority: str = None,
        project: str = None,
        active_only: bool = True
    ) -> List[Dict]:
        """
        Get AI instructions by criteria.

        Args:
            scope: Filter by scope (or 'all' for global + current project)
            category: Filter by category
            priority: Filter by priority
            project: Project name
            active_only: Only return active instructions

        Returns:
            List of instructions sorted by priority, category, date

        Special scope 'all': Returns global + project-specific instructions
        """
        cursor = self.conn.cursor()

        where_clauses = []
        params = []

        if active_only:
            where_clauses.append("ai.active = 1")

        if scope:
            if scope == 'all':
                project_name = project or Path.cwd().name
                project_id = self.db.get_or_create_project(project_name)
                where_clauses.append("(ai.scope = 'global' OR (ai.scope = 'project' AND ai.project_id = ?))")
                params.append(project_id)
            else:
                where_clauses.append("ai.scope = ?")
                params.append(scope)

        if category:
            where_clauses.append("ai.category = ?")
            params.append(category)

        if priority:
            where_clauses.append("ai.priority = ?")
            params.append(priority)

        if project and scope != 'all':
            project_id = self.db.get_or_create_project(project)
            where_clauses.append("ai.project_id = ?")
            params.append(project_id)

        where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        created_expr = format_timestamp_sql('ai.created_at', 'localtime')
        updated_expr = format_timestamp_sql('ai.updated_at', 'localtime')

        cursor.execute(f"""
            SELECT
                ai.*,
                p.name as project_name,
                {created_expr} as created,
                {updated_expr} as updated
            FROM ai_instructions ai
            LEFT JOIN projects p ON ai.project_id = p.id
            {where_sql}
            ORDER BY
                CASE ai.priority
                    WHEN 'must' THEN 1
                    WHEN 'should' THEN 2
                    WHEN 'nice' THEN 3
                    ELSE 4
                END,
                ai.category,
                ai.created_at DESC
        """, params)

        return [dict(row) for row in cursor.fetchall()]

    def search(self, query: str, limit: int = 20) -> List[Dict]:
        """
        Search in AI instructions using full-text search.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching instructions with snippets

        Uses PostgreSQL tsvector @@ plainto_tsquery with ts_rank.
        Search order: rank DESC, usage_count DESC, created_at DESC
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT
                ai.*,
                p.name as project_name,
                SUBSTRING(ai.instruction, 1, 100) as snippet,
                ts_rank(search_vector, plainto_tsquery('english', ?)) as rank
            FROM ai_instructions ai
            LEFT JOIN projects p ON ai.project_id = p.id
            WHERE search_vector @@ plainto_tsquery('english', ?)
            ORDER BY rank DESC, ai.usage_count DESC, ai.created_at DESC
            LIMIT ?
        """, (query, query, limit))

        return [dict(row) for row in cursor.fetchall()]

    def update_usage(self, instruction_id: int) -> None:
        """
        Increment usage counter for instruction.

        Args:
            instruction_id: Instruction ID

        Called when instruction is used in an AI prompt.
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            UPDATE ai_instructions
            SET usage_count = usage_count + 1,
                updated_at = EXTRACT(epoch FROM now())::bigint
            WHERE id = ?
        """, (instruction_id,))
        self.conn.commit()

    def toggle(self, instruction_id: int) -> bool:
        """
        Toggle instruction active status.

        Args:
            instruction_id: Instruction ID

        Returns:
            New active status (True/False)
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            UPDATE ai_instructions
            SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END,
                updated_at = EXTRACT(epoch FROM now())::bigint
            WHERE id = ?
        """, (instruction_id,))
        self.conn.commit()

        cursor.execute("SELECT active FROM ai_instructions WHERE id = ?", (instruction_id,))
        result = cursor.fetchone()
        return bool(result['active']) if result else False

    def update(
        self,
        instruction_id: int,
        scope: str = None,
        priority: str = None,
        category: str = None,
        instruction: str = None,
        rationale: str = None,
        examples: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
        clear_examples: bool = False,
        clear_rationale: bool = False
    ) -> bool:
        """
        Update instruction metadata.

        Args:
            instruction_id: Instruction ID
            scope: New scope (optional)
            priority: New priority (optional)
            category: New category (optional)

        Returns:
            True if updated, False if instruction not found or invalid params

        Security: Validates scope and priority values
        """
        cursor = self.conn.cursor()

        cursor.execute("SELECT * FROM ai_instructions WHERE id = ?", (instruction_id,))
        instruction_row = cursor.fetchone()
        if not instruction_row:
            return False

        updates = []
        params = []

        if scope is not None:
            if scope not in self.VALID_SCOPES:
                print(f"❌ Invalid scope: {scope} (allowed: {', '.join(sorted(self.VALID_SCOPES))})")
                return False
            updates.append("scope = ?")
            params.append(scope)

            if scope == 'global':
                updates.append("project_id = NULL")
            elif scope == 'project' and instruction_row['project_id'] is None:
                project_id = self.db.get_or_create_project(Path.cwd().name)
                updates.append("project_id = ?")
                params.append(project_id)

        if priority is not None:
            if priority not in self.VALID_PRIORITIES:
                print(f"❌ Invalid priority: {priority} (allowed: {', '.join(sorted(self.VALID_PRIORITIES))})")
                return False
            updates.append("priority = ?")
            params.append(priority)

        if category is not None:
            updates.append("category = ?")
            params.append(category)

        if instruction is not None:
            instruction = instruction.strip()
            if not instruction:
                print("❌ Instruction text must not be empty")
                return False
            updates.append("instruction = ?")
            params.append(instruction)

        if rationale is not None:
            updates.append("rationale = ?")
            params.append(rationale)
        elif clear_rationale:
            updates.append("rationale = NULL")

        if examples is not None:
            updates.append("examples = ?")
            params.append(json.dumps(examples) if examples else None)
        elif clear_examples:
            updates.append("examples = NULL")

        if metadata is not None:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata) if metadata else None)

        if not updates:
            print("❌ No updates specified")
            return False

        updates.append("updated_at = EXTRACT(epoch FROM now())::bigint")

        query = f"UPDATE ai_instructions SET {', '.join(updates)} WHERE id = ?"
        params.append(instruction_id)

        try:
            cursor.execute(query, params)

            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            raise

    def delete(self, instruction_id: int) -> bool:
        """
        Delete an AI instruction.

        Args:
            instruction_id: Instruction ID

        Returns:
            True if deleted, False if not found

        Security: Uses parameterized query
        """
        cursor = self.conn.cursor()

        try:
            cursor.execute("DELETE FROM ai_instructions WHERE id = ?", (instruction_id,))

            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            self.conn.rollback()
            raise

    def search_filtered(
        self,
        query: str = None,
        category: str = None,
        priority: str = None,
        scope: str = None,
        project: str = None,
        limit: int = 20
    ) -> List[Dict]:
        """
        Advanced search in AI instructions with multiple filters.

        Args:
            query: Full-text search query (optional)
            category: Filter by category (infrastructure, security, etc.)
            priority: Filter by priority (must, should, nice)
            scope: Filter by scope (global, project, session)
            project: Filter by project name
            limit: Maximum results

        Returns:
            List of matching instructions with metadata

        Features:
            - Combines full-text search with exact filters
            - Searches in metadata JSON for aliases/tags
            - Uses PostgreSQL tsvector for full-text search
            - Ordered by relevance (rank) then usage_count

        Example:
            # Find SSH hostnames
            search_filtered(query="wolf prod ssh", category="infrastructure")

            # Find security rules
            search_filtered(category="security", priority="must")
        """
        cursor = self.conn.cursor()

        where_clauses = []
        params = []

        # Full-text search (optional)
        if query:
            where_clauses.append("""
                (search_vector @@ plainto_tsquery('english', ?)
                 OR metadata::text ILIKE ?)
            """)
            params.extend([query, f'%{query}%'])

        # Category filter
        if category:
            where_clauses.append("ai.category = ?")
            params.append(category)

        # Priority filter
        if priority:
            where_clauses.append("ai.priority = ?")
            params.append(priority)

        # Scope filter
        if scope:
            where_clauses.append("ai.scope = ?")
            params.append(scope)

        # Project filter
        if project:
            where_clauses.append("p.name = ?")
            params.append(project)

        # Build WHERE clause
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Build query with ts_rank for relevance
        rank_sql = ""
        if query:
            rank_sql = ", ts_rank(search_vector, plainto_tsquery('english', ?)) as rank"
            rank_params = [query]
        else:
            rank_sql = ", 0 as rank"
            rank_params = []

        sql = f"""
            SELECT
                ai.*,
                p.name as project_name,
                SUBSTRING(ai.instruction, 1, 150) as snippet
                {rank_sql}
            FROM ai_instructions ai
            LEFT JOIN projects p ON ai.project_id = p.id
            WHERE {where_sql}
            ORDER BY rank DESC, ai.usage_count DESC, ai.created_at DESC
            LIMIT ?
        """
        cursor.execute(sql, rank_params + params + [limit])

        return [dict(row) for row in cursor.fetchall()]
