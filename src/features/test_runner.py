"""
Test Runner Feature for ContextWolf
Handles test execution, result tracking, and reporting

Features:
- Execute test cases with timeout protection
- Capture stdout/stderr with size limits
- Security: Input sanitization, command validation
- Result tracking and history
- Environment variable isolation

Security Measures:
- Command sanitization (no shell injection)
- Timeout enforcement (max 1 hour)
- Output size limits (prevent memory exhaustion)
- Working directory validation
- No arbitrary code execution without validation
"""

import subprocess
import time
import json
import zlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from src.core.database import Database
from src.core.helpers import InputValidator, format_timestamp
from src.domain.actions import ActionManager


class TestSecurityValidator:
    """
    Security validator for test commands and inputs.
    Implements defense-in-depth approach.
    """

    MAX_COMMAND_LENGTH = 2000
    MAX_WORKING_DIR_LENGTH = 500
    MAX_OUTPUT_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_TIMEOUT = 3600  # 1 hour

    # Dangerous patterns that should trigger warnings
    DANGEROUS_PATTERNS = [
        'rm -rf /',
        'mkfs.',
        ':(){ :|:& };:',  # Fork bomb
        '/dev/sda',
        'dd if=',
        'format c:',
        '> /dev/null',  # Suspicious redirection
    ]

    @classmethod
    def sanitize_command(cls, command: str) -> str:
        """
        Sanitize test command.

        Args:
            command: Command to execute

        Returns:
            Sanitized command string

        Raises:
            ValueError: If command is invalid or dangerous
        """
        if not command or not command.strip():
            raise ValueError("Command cannot be empty")

        command = command.strip()

        # Length check
        if len(command) > cls.MAX_COMMAND_LENGTH:
            raise ValueError(f"Command too long (max {cls.MAX_COMMAND_LENGTH} chars)")

        # Dangerous pattern check
        command_lower = command.lower()
        for pattern in cls.DANGEROUS_PATTERNS:
            if pattern in command_lower:
                raise ValueError(f"Dangerous command pattern detected: {pattern}")

        return command

    @classmethod
    def validate_timeout(cls, timeout: int) -> int:
        """
        Validate and sanitize timeout value.

        Args:
            timeout: Timeout in seconds

        Returns:
            Valid timeout value

        Raises:
            ValueError: If timeout is invalid
        """
        if not isinstance(timeout, int):
            raise ValueError("Timeout must be an integer")

        if timeout <= 0:
            raise ValueError("Timeout must be positive")

        if timeout > cls.MAX_TIMEOUT:
            raise ValueError(f"Timeout too high (max {cls.MAX_TIMEOUT} seconds)")

        return timeout

    @classmethod
    def validate_working_directory(cls, working_dir: str) -> Path:
        """
        Validate working directory.

        Args:
            working_dir: Directory path

        Returns:
            Validated Path object

        Raises:
            ValueError: If directory is invalid
        """
        if not working_dir:
            raise ValueError("Working directory cannot be empty")

        if len(working_dir) > cls.MAX_WORKING_DIR_LENGTH:
            raise ValueError(f"Path too long (max {cls.MAX_WORKING_DIR_LENGTH} chars)")

        path = Path(working_dir).expanduser().resolve()

        if not path.exists():
            raise ValueError(f"Directory does not exist: {path}")

        if not path.is_dir():
            raise ValueError(f"Not a directory: {path}")

        return path

    @classmethod
    def truncate_output(cls, output: str, max_size: int = MAX_OUTPUT_SIZE) -> str:
        """
        Truncate output to prevent memory exhaustion.

        Args:
            output: Output string
            max_size: Maximum size in bytes

        Returns:
            Truncated output with marker if truncated
        """
        if len(output) <= max_size:
            return output

        truncated = output[:max_size]
        return truncated + f"\n\n[... Output truncated at {max_size} bytes ...]"


class TestExecutionResult:
    """Data class for test execution results"""

    def __init__(
        self,
        status: str,
        exit_code: int,
        duration_ms: int,
        stdout: str = "",
        stderr: str = "",
        error_message: str = None
    ):
        self.status = status
        self.exit_code = exit_code
        self.duration_ms = duration_ms
        self.stdout = stdout
        self.stderr = stderr
        self.error_message = error_message

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'status': self.status,
            'exit_code': self.exit_code,
            'duration_ms': self.duration_ms,
            'stdout': self.stdout,
            'stderr': self.stderr,
            'error_message': self.error_message
        }


class TestRunner:
    """
    Manages test execution and result tracking.

    Responsibilities:
    - Execute test cases safely
    - Capture and store results
    - Track execution history
    - Provide execution statistics
    """

    def __init__(self, db: Database):
        """Initialize with database connection"""
        self.db = db
        self.action_manager = ActionManager(db)
        self.validator = InputValidator()
        self.security = TestSecurityValidator()

    def execute_test_case(
        self,
        test_case_id: int,
        environment: Dict[str, str] = None,
        save_full_output: bool = True
    ) -> TestExecutionResult:
        """
        Execute a single test case.

        Args:
            test_case_id: ID of the test case to execute
            environment: Additional environment variables
            save_full_output: Whether to save full output (compressed)

        Returns:
            TestExecutionResult with execution details

        Raises:
            ValueError: If test case not found or invalid
        """
        # 1. Load test case from database
        test_case = self._load_test_case(test_case_id)
        if not test_case:
            raise ValueError(f"Test case not found: {test_case_id}")

        if not test_case['active']:
            raise ValueError(f"Test case is inactive: {test_case_id}")

        # 2. Security validation
        command = self.security.sanitize_command(test_case['command'])
        timeout = self.security.validate_timeout(test_case['timeout'])

        working_dir = None
        if test_case['working_directory']:
            working_dir = self.security.validate_working_directory(
                test_case['working_directory']
            )

        # 3. Execute command
        result = self._execute_command(
            command=command,
            timeout=timeout,
            working_dir=working_dir,
            environment=environment
        )

        # 4. Determine status based on expected exit code
        expected_exit_code = test_case['expected_exit_code']
        if result.status == 'completed':
            if result.exit_code == expected_exit_code:
                result.status = 'passed'
            else:
                result.status = 'failed'

        # 5. Save execution result to database
        execution_id = self._save_execution_result(
            test_case_id=test_case_id,
            result=result,
            save_full_output=save_full_output,
            environment_snapshot=environment
        )

        result.execution_id = execution_id
        return result

    def _execute_command(
        self,
        command: str,
        timeout: int,
        working_dir: Path = None,
        environment: Dict[str, str] = None
    ) -> TestExecutionResult:
        """
        Execute command with security measures.

        Uses subprocess.run() with:
        - Timeout protection
        - Output capture
        - No shell injection (shell=False)
        - Environment isolation

        Args:
            command: Sanitized command to execute
            timeout: Timeout in seconds
            working_dir: Working directory
            environment: Environment variables

        Returns:
            TestExecutionResult
        """
        start_time = time.time()

        try:
            # Prepare environment
            import os
            env = os.environ.copy()
            if environment:
                env.update(environment)

            # Execute command
            # IMPORTANT: shell=False prevents shell injection
            # Command is split by shlex for proper argument parsing
            import shlex
            cmd_args = shlex.split(command)

            result = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,  # Don't raise on non-zero exit
                cwd=str(working_dir) if working_dir else None,
                env=env
            )

            duration_ms = int((time.time() - start_time) * 1000)

            # Truncate output for security
            stdout = self.security.truncate_output(result.stdout)
            stderr = self.security.truncate_output(result.stderr)

            return TestExecutionResult(
                status='completed',
                exit_code=result.returncode,
                duration_ms=duration_ms,
                stdout=stdout,
                stderr=stderr
            )

        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start_time) * 1000)
            return TestExecutionResult(
                status='timeout',
                exit_code=-1,
                duration_ms=duration_ms,
                error_message=f"Test exceeded timeout of {timeout}s"
            )

        except FileNotFoundError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return TestExecutionResult(
                status='error',
                exit_code=-1,
                duration_ms=duration_ms,
                error_message=f"Command not found: {str(e)}"
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return TestExecutionResult(
                status='error',
                exit_code=-1,
                duration_ms=duration_ms,
                error_message=f"Execution error: {str(e)}"
            )

    def _load_test_case(self, test_case_id: int) -> Optional[Dict[str, Any]]:
        """Load test case from database"""
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
        if not row:
            return None

        return dict(row)

    def _save_execution_result(
        self,
        test_case_id: int,
        result: TestExecutionResult,
        save_full_output: bool,
        environment_snapshot: Dict[str, str] = None
    ) -> int:
        """
        Save execution result to database.

        Args:
            test_case_id: Test case ID
            result: Execution result
            save_full_output: Whether to compress and save full output
            environment_snapshot: Environment variables used

        Returns:
            Execution ID
        """
        cursor = self.db.conn.cursor()

        # Create compressed output if requested
        full_output_compressed = None
        if save_full_output and (result.stdout or result.stderr):
            full_output = json.dumps({
                'stdout': result.stdout,
                'stderr': result.stderr,
                'error_message': result.error_message
            })
            full_output_compressed = zlib.compress(full_output.encode('utf-8'))

        # Create environment snapshot
        env_snapshot = None
        if environment_snapshot:
            env_snapshot = json.dumps(environment_snapshot)

        # Preview for quick display (first 500 chars)
        stdout_preview = result.stdout[:500] if result.stdout else None
        stderr_preview = result.stderr[:500] if result.stderr else None

        cursor.execute("""
            INSERT INTO test_executions (
                test_case_id, status, exit_code, duration_ms,
                stdout_preview, stderr_preview, full_output_compressed,
                environment_snapshot, executed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, EXTRACT(epoch FROM now())::bigint)
            RETURNING id
        """, (
            test_case_id,
            result.status,
            result.exit_code,
            result.duration_ms,
            stdout_preview,
            stderr_preview,
            full_output_compressed,
            env_snapshot
        ))

        execution_id = cursor.fetchone()['id']
        self.db.conn.commit()

        return execution_id

    def get_test_history(
        self,
        test_case_id: int,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get execution history for a test case.

        Args:
            test_case_id: Test case ID
            limit: Maximum number of results

        Returns:
            List of execution records
        """
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT
                id,
                status,
                exit_code,
                duration_ms,
                stdout_preview,
                stderr_preview,
                executed_at
            FROM test_executions
            WHERE test_case_id = ?
            ORDER BY executed_at DESC
            LIMIT ?
        """, (test_case_id, limit))

        return [dict(row) for row in cursor.fetchall()]

    def get_full_output(self, execution_id: int) -> Optional[Dict[str, str]]:
        """
        Retrieve full output from a test execution.

        Args:
            execution_id: Execution ID

        Returns:
            Dictionary with stdout, stderr, error_message
        """
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT full_output_compressed
            FROM test_executions
            WHERE id = ?
        """, (execution_id,))

        row = cursor.fetchone()
        if not row or not row['full_output_compressed']:
            return None

        try:
            decompressed = zlib.decompress(row['full_output_compressed'])
            return json.loads(decompressed.decode('utf-8'))
        except Exception as e:
            print(f"Error decompressing output: {e}")
            return None
