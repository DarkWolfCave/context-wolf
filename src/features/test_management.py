"""
Test Management Feature for ContextWolf
Handles test suites, test cases, and test organization

Features:
- Create and manage test suites
- Add test cases to suites
- Organize tests by project
- Tag-based filtering
- Bulk operations

Security:
- Input sanitization on all text fields
- Size limits on descriptions
- Command validation before storage
"""

import json
from typing import List, Dict, Optional, Any
from src.core.database import Database
from src.core.helpers import InputValidator
from src.features.test_runner import TestSecurityValidator


class TestSanitizer:
    """
    Security sanitizer for test management inputs.
    Follows the GOLDEN RULE: "Traue NIEMALS User-Input!"
    """

    MAX_NAME_LENGTH = 200
    MAX_DESCRIPTION_LENGTH = 10240  # 10KB
    MAX_COMMAND_LENGTH = 2000
    MAX_TAG_LENGTH = 50
    MAX_TAGS_COUNT = 20

    @classmethod
    def sanitize_test_data(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize all test-related input data.

        Implements defense-in-depth:
        1. Remove control characters and null bytes
        2. Enforce length limits
        3. Validate required fields
        4. Sanitize arrays/lists

        Args:
            data: Input data dictionary

        Returns:
            Sanitized data dictionary

        Raises:
            ValueError: If required fields are missing or invalid
        """
        # Use InputValidator from core.helpers (Python standard library only)
        validator = InputValidator()

        sanitized = {}

        # Name (required)
        if 'name' in data:
            name = validator.clean_text(str(data['name']), max_length=cls.MAX_NAME_LENGTH)
            if not name.strip():
                raise ValueError('Name cannot be empty')
            sanitized['name'] = name.strip()

        # Description (optional)
        if 'description' in data:
            desc = validator.clean_text(str(data['description']), max_length=cls.MAX_DESCRIPTION_LENGTH)
            sanitized['description'] = desc

        # Command (for test cases)
        if 'command' in data:
            # Use TestSecurityValidator for command validation
            command = TestSecurityValidator.sanitize_command(data['command'])
            sanitized['command'] = command

        # Tags (array sanitization)
        if 'tags' in data:
            tags = cls._sanitize_tags(data['tags'])
            sanitized['tags'] = tags

        # Working directory (path validation)
        if 'working_directory' in data and data['working_directory']:
            working_dir = validator.clean_text(str(data['working_directory']), max_length=500)
            sanitized['working_directory'] = working_dir

        # Timeout (integer validation)
        if 'timeout' in data:
            timeout = TestSecurityValidator.validate_timeout(int(data['timeout']))
            sanitized['timeout'] = timeout

        # Expected exit code (integer validation)
        if 'expected_exit_code' in data:
            exit_code = int(data['expected_exit_code'])
            if exit_code < -1 or exit_code > 255:
                raise ValueError('Invalid exit code (must be -1 to 255)')
            sanitized['expected_exit_code'] = exit_code

        # Priority (whitelist validation)
        if 'priority' in data:
            priority = str(data['priority']).lower()
            if priority not in ['critical', 'high', 'normal', 'low']:
                raise ValueError('Invalid priority (must be critical/high/normal/low)')
            sanitized['priority'] = priority

        return sanitized

    @classmethod
    def _sanitize_tags(cls, tags: Any) -> List[str]:
        """
        Sanitize tag list.

        Args:
            tags: Tags as list or comma-separated string

        Returns:
            Sanitized list of tags

        Raises:
            ValueError: If too many tags or invalid format
        """
        validator = InputValidator()

        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(',')]
        elif not isinstance(tags, list):
            tags = []

        # Sanitize each tag
        sanitized = []
        for tag in tags[:cls.MAX_TAGS_COUNT]:
            tag = validator.clean_text(str(tag), max_length=cls.MAX_TAG_LENGTH).strip()
            if tag:
                sanitized.append(tag)

        if len(sanitized) > cls.MAX_TAGS_COUNT:
            raise ValueError(f'Too many tags (max {cls.MAX_TAGS_COUNT})')

        return sanitized


class TestManager:
    """
    Manages test suites and test cases.

    Responsibilities:
    - Create and organize test suites
    - Add and manage test cases
    - Tag-based filtering
    - Bulk operations
    """

    def __init__(self, db: Database):
        """Initialize with database connection"""
        self.db = db
        self.validator = InputValidator()
        self.sanitizer = TestSanitizer()

    def create_test_suite(
        self,
        name: str,
        project_name: str,
        description: str = None,
        tags: List[str] = None
    ) -> int:
        """
        Create a new test suite.

        Args:
            name: Suite name
            project_name: Project to associate with
            description: Optional description
            tags: Optional tags

        Returns:
            Suite ID

        Raises:
            ValueError: If validation fails
        """
        # Sanitize inputs
        data = self.sanitizer.sanitize_test_data({
            'name': name,
            'description': description,
            'tags': tags or []
        })

        # Get or create project
        project_id = self.db.get_or_create_project(project_name)

        # Serialize tags
        tags_json = json.dumps(data.get('tags', [])) if data.get('tags') else None

        cursor = self.db.conn.cursor()
        cursor.execute("""
            INSERT INTO test_suites (name, description, project_id, tags, created_at)
            VALUES (?, ?, ?, ?, EXTRACT(epoch FROM now())::bigint)
            RETURNING id
        """, (
            data['name'],
            data.get('description'),
            project_id,
            tags_json
        ))
        suite_id = cursor.fetchone()['id']

        self.db.conn.commit()
        return suite_id

    def add_test_case(
        self,
        suite_id: int,
        name: str,
        command: str,
        description: str = None,
        working_directory: str = None,
        timeout: int = 300,
        expected_exit_code: int = 0,
        tags: List[str] = None,
        priority: str = 'normal'
    ) -> int:
        """
        Add a test case to a suite.

        Args:
            suite_id: Test suite ID
            name: Test case name
            command: Command to execute
            description: Optional description
            working_directory: Optional working directory
            timeout: Timeout in seconds (default 300 = 5 minutes)
            expected_exit_code: Expected exit code (default 0)
            tags: Optional tags
            priority: Priority level (critical/high/normal/low)

        Returns:
            Test case ID

        Raises:
            ValueError: If validation fails or suite not found
        """
        # Verify suite exists
        if not self._suite_exists(suite_id):
            raise ValueError(f"Test suite not found: {suite_id}")

        # Sanitize inputs (includes command validation!)
        data = self.sanitizer.sanitize_test_data({
            'name': name,
            'command': command,
            'description': description,
            'working_directory': working_directory,
            'timeout': timeout,
            'expected_exit_code': expected_exit_code,
            'tags': tags or [],
            'priority': priority
        })

        # Serialize tags
        tags_json = json.dumps(data.get('tags', [])) if data.get('tags') else None

        cursor = self.db.conn.cursor()
        cursor.execute("""
            INSERT INTO test_cases (
                suite_id, name, description, command,
                working_directory, timeout, expected_exit_code,
                tags, priority, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, EXTRACT(epoch FROM now())::bigint)
            RETURNING id
        """, (
            suite_id,
            data['name'],
            data.get('description'),
            data['command'],
            data.get('working_directory'),
            data.get('timeout', 300),
            data.get('expected_exit_code', 0),
            tags_json,
            data.get('priority', 'normal')
        ))
        test_case_id = cursor.fetchone()['id']

        self.db.conn.commit()
        return test_case_id

    def list_test_suites(
        self,
        project_name: str = None,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        List test suites.

        Args:
            project_name: Filter by project (None = all projects)
            active_only: Only show active suites

        Returns:
            List of test suite records
        """
        cursor = self.db.conn.cursor()

        query = """
            SELECT
                ts.id, ts.name, ts.description, ts.project_id,
                ts.tags, ts.created_at, ts.active,
                p.name as project_name,
                COUNT(tc.id) as test_count
            FROM test_suites ts
            JOIN projects p ON ts.project_id = p.id
            LEFT JOIN test_cases tc ON ts.id = tc.suite_id AND tc.active = 1
            WHERE 1=1
        """

        params = []

        if active_only:
            query += " AND ts.active = 1"

        if project_name:
            query += " AND p.name = ?"
            params.append(project_name)

        query += " GROUP BY ts.id, ts.name, ts.description, ts.project_id, ts.tags, ts.created_at, ts.active, p.name ORDER BY ts.name"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def list_test_cases(
        self,
        suite_id: int = None,
        active_only: bool = True,
        priority: str = None
    ) -> List[Dict[str, Any]]:
        """
        List test cases.

        Args:
            suite_id: Filter by suite (None = all suites)
            active_only: Only show active test cases
            priority: Filter by priority

        Returns:
            List of test case records
        """
        cursor = self.db.conn.cursor()

        query = """
            SELECT
                tc.*,
                ts.name as suite_name,
                ts.project_id
            FROM test_cases tc
            JOIN test_suites ts ON tc.suite_id = ts.id
            WHERE 1=1
        """
        params = []

        if suite_id:
            query += " AND tc.suite_id = ?"
            params.append(suite_id)

        if active_only:
            query += " AND tc.active = 1"

        if priority:
            query += " AND tc.priority = ?"
            params.append(priority)

        query += " ORDER BY tc.priority DESC, tc.name"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_test_case(self, test_case_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a single test case by ID.

        Args:
            test_case_id: Test case ID

        Returns:
            Test case record or None
        """
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT
                tc.*,
                ts.name as suite_name,
                ts.project_id
            FROM test_cases tc
            JOIN test_suites ts ON tc.suite_id = ts.id
            WHERE tc.id = ?
        """, (test_case_id,))

        row = cursor.fetchone()
        return dict(row) if row else None

    def update_test_case(
        self,
        test_case_id: int,
        **kwargs
    ) -> bool:
        """
        Update a test case.

        Args:
            test_case_id: Test case ID
            **kwargs: Fields to update (name, command, timeout, etc.)

        Returns:
            True if updated

        Raises:
            ValueError: If validation fails
        """
        # Sanitize updates
        data = self.sanitizer.sanitize_test_data(kwargs)

        if not data:
            return False

        # Build UPDATE query
        ALLOWED_FIELDS = {'name', 'description', 'command', 'tags', 'working_directory', 'timeout', 'expected_exit_code', 'priority'}
        fields = []
        values = []
        for key, value in data.items():
            if key not in ALLOWED_FIELDS:
                continue
            fields.append(f"{key} = ?")
            values.append(value)

        fields.append("updated_at = EXTRACT(epoch FROM now())::bigint")
        values.append(test_case_id)

        query = f"UPDATE test_cases SET {', '.join(fields)} WHERE id = ?"

        cursor = self.db.conn.cursor()
        cursor.execute(query, values)
        self.db.conn.commit()

        return cursor.rowcount > 0

    def update_test_suite(
        self,
        suite_id: int,
        **kwargs
    ) -> bool:
        """
        Update a test suite.

        Args:
            suite_id: Test suite ID
            **kwargs: Fields to update (name, description, tags)

        Returns:
            True if updated

        Raises:
            ValueError: If validation fails or suite not found
        """
        # Verify suite exists
        if not self._suite_exists(suite_id):
            raise ValueError(f"Test suite not found: {suite_id}")

        # Sanitize updates
        data = self.sanitizer.sanitize_test_data(kwargs)

        if not data:
            return False

        # Handle tags serialization
        if 'tags' in data:
            data['tags'] = json.dumps(data['tags']) if data['tags'] else None

        ALLOWED_FIELDS = {'name', 'description', 'tags'}
        fields = []
        values = []
        for key, value in data.items():
            if key not in ALLOWED_FIELDS:
                continue
            fields.append(f"{key} = ?")
            values.append(value)

        fields.append("updated_at = EXTRACT(epoch FROM now())::bigint")

        values.append(suite_id)

        query = f"UPDATE test_suites SET {', '.join(fields)} WHERE id = ?"

        cursor = self.db.conn.cursor()
        cursor.execute(query, values)
        self.db.conn.commit()

        return cursor.rowcount > 0

    def deactivate_test_case(self, test_case_id: int) -> bool:
        """
        Deactivate a test case (soft delete).

        Args:
            test_case_id: Test case ID

        Returns:
            True if deactivated
        """
        cursor = self.db.conn.cursor()
        cursor.execute("""
            UPDATE test_cases
            SET active = 0, updated_at = EXTRACT(epoch FROM now())::bigint
            WHERE id = ?
        """, (test_case_id,))

        self.db.conn.commit()
        return cursor.rowcount > 0

    def deactivate_test_suite(self, suite_id: int) -> bool:
        """
        Deactivate a test suite (soft delete).

        Args:
            suite_id: Test suite ID

        Returns:
            True if deactivated
        """
        cursor = self.db.conn.cursor()
        cursor.execute("""
            UPDATE test_suites
            SET active = 0, updated_at = EXTRACT(epoch FROM now())::bigint
            WHERE id = ?
        """, (suite_id,))

        self.db.conn.commit()
        return cursor.rowcount > 0

    def _suite_exists(self, suite_id: int) -> bool:
        """Check if suite exists"""
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT 1 FROM test_suites WHERE id = ?", (suite_id,))
        return cursor.fetchone() is not None
