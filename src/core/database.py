"""
Database Layer for ContextWolf
PostgreSQL backend with SmartConnection auto-reconnect.
"""

from typing import Dict
import logging

from .backends import BackendFactory, DatabaseBackend

logger = logging.getLogger(__name__)


def _is_connection_error(e: Exception) -> bool:
    """Check if exception is a database connection error"""
    error_str = str(e).lower()
    return any(kw in error_str for kw in ('closed', 'connection', 'server', 'timeout', 'broken pipe'))


class SmartCursor:
    """
    Cursor wrapper with auto-reconnect and placeholder conversion.

    Converts '?' to '%s' for PostgreSQL compatibility.
    On connection errors, triggers reconnect via backend and retries once.
    """

    def __init__(self, real_cursor, backend=None):
        """
        Initialize smart cursor.

        Args:
            real_cursor: Actual database cursor
            backend: DatabaseBackend reference for auto-reconnect
        """
        self._cursor = real_cursor
        self._backend = backend

    def _reconnect_and_get_cursor(self):
        """Reconnect via backend and return fresh cursor"""
        if self._backend and hasattr(self._backend, '_ensure_connection'):
            logger.warning("🔄 SmartCursor: Connection lost, triggering reconnect...")
            self._backend._ensure_connection()
            self._cursor = self._backend.conn.cursor()
            return True
        return False

    def execute(self, query: str, params=None):
        """Execute query with auto-reconnect and placeholder conversion"""
        if '?' in query:
            query = query.replace('?', '%s')

        try:
            if params:
                self._cursor.execute(query, params)
            else:
                self._cursor.execute(query)
        except Exception as e:
            if _is_connection_error(e):
                if self._reconnect_and_get_cursor():
                    if params:
                        self._cursor.execute(query, params)
                    else:
                        self._cursor.execute(query)
                else:
                    raise
            else:
                raise

        # Return self for iteration support (e.g., for row in cursor.execute(...))
        return self

    def executemany(self, query: str, params_list):
        """Execute many with auto-reconnect and placeholder conversion"""
        if '?' in query:
            query = query.replace('?', '%s')

        try:
            return self._cursor.executemany(query, params_list)
        except Exception as e:
            if _is_connection_error(e):
                if self._reconnect_and_get_cursor():
                    return self._cursor.executemany(query, params_list)
            raise

    def fetchone(self):
        """Fetch one row"""
        return self._cursor.fetchone()

    def fetchall(self):
        """Fetch all rows"""
        return self._cursor.fetchall()

    def fetchmany(self, size=None):
        """Fetch many rows"""
        if size:
            return self._cursor.fetchmany(size)
        return self._cursor.fetchmany()

    def __iter__(self):
        """Make cursor iterable"""
        return iter(self._cursor)

    def __next__(self):
        """Support for iteration protocol"""
        return next(self._cursor)

    @property
    def rowcount(self):
        """Return rowcount"""
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        """Return last row id"""
        return self._cursor.lastrowid

    def close(self):
        """Close cursor"""
        return self._cursor.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class SmartConnection:
    """
    Connection wrapper with auto-reconnect support.

    Returns SmartCursor instances with placeholder conversion.
    Checks connection health before creating cursors and passes
    backend reference for auto-reconnect in SmartCursor.
    """

    def __init__(self, real_connection, backend=None):
        """
        Initialize smart connection.

        Args:
            real_connection: Actual database connection
            backend: DatabaseBackend reference for auto-reconnect
        """
        self._connection = real_connection
        self._backend = backend

    def cursor(self):
        """Return SmartCursor with auto-reconnect support"""
        if self._backend and hasattr(self._backend, '_ensure_connection'):
            try:
                self._backend._ensure_connection()
                self._connection = self._backend.conn
            except Exception as e:
                logger.error(f"SmartConnection: Failed to ensure connection: {e}")

        real_cursor = self._connection.cursor()
        return SmartCursor(real_cursor, backend=self._backend)

    def commit(self):
        """Commit transaction (no-op if autocommit is enabled)"""
        if not getattr(self._connection, 'autocommit', False):
            return self._connection.commit()

    def rollback(self):
        """Rollback transaction (no-op if autocommit is enabled)"""
        if not getattr(self._connection, 'autocommit', False):
            return self._connection.rollback()

    def close(self):
        """Close connection"""
        return self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        return False

    # Expose other common connection attributes/methods
    def __getattr__(self, name):
        """Delegate unknown attributes to real connection"""
        return getattr(self._connection, name)


class Database:
    """
    PostgreSQL database wrapper with connection pooling and auto-reconnect.

    Usage:
        db = Database()  # Auto-loads config
        project_id = db.get_or_create_project("my-project")
        db.close()
    """

    def __init__(self, config=None):
        """
        Initialize database connection.

        Args:
            config: Config object (optional, auto-loads if not provided)
        """
        if config is None:
            from .config import Config
            config = Config()

        self.config = config

        # Create backend
        self.backend: DatabaseBackend = BackendFactory.create(self.config)

        # Connect to database
        self.backend.connect()

        # Run pending migrations (creates schema on fresh DB, updates on existing)
        self._run_migrations()

        # Caches for performance
        self._project_cache: Dict[str, int] = {}
        self._type_cache: Dict[str, int] = {}

        logger.info(f"✅ Database initialized with {self.backend.__class__.__name__}")

    @property
    def conn(self):
        """
        Provide SmartConnection with auto-reconnect.

        Returns SmartConnection that:
        - Converts ? to %s for PostgreSQL
        - Auto-reconnects on connection errors
        - Passes backend reference for SmartCursor reconnect support
        """
        return SmartConnection(self.backend.conn, backend=self.backend)

    def _run_migrations(self) -> None:
        """Run pending database migrations."""
        from .migrator import run_migrations
        count = run_migrations(self.backend)
        if count > 0:
            logger.info(f"✅ {count} migration(s) applied")

    def get_or_create_project(self, project_name: str) -> int:
        """
        Get or create project, returning its ID.

        Args:
            project_name: Name of the project (required)

        Returns:
            Project ID

        Security: Uses parameterized queries
        """
        if not project_name or not project_name.strip():
            project_name = "default"

        # Check cache
        if project_name in self._project_cache:
            # Update last_active
            self.backend.execute(
                "UPDATE projects SET last_active = ? WHERE id = ?",
                (self._get_current_timestamp(), self._project_cache[project_name])
            )
            return self._project_cache[project_name]

        # Insert or get project
        result = self.backend.fetchone(
            """
            INSERT INTO projects (name) VALUES (%s)
            ON CONFLICT (name) DO UPDATE SET last_active = EXTRACT(EPOCH FROM NOW())::BIGINT
            RETURNING id
            """,
            (project_name,)
        )

        project_id = result['id']
        self._project_cache[project_name] = project_id
        self.backend.commit()
        return project_id

    def get_or_create_type(self, type_name: str) -> int:
        """
        Get or create action type, returning its ID.

        Args:
            type_name: Name of the action type

        Returns:
            Type ID

        Security: Uses parameterized queries
        """
        # Check cache
        if type_name in self._type_cache:
            return self._type_cache[type_name]

        # Insert or get type
        result = self.backend.fetchone(
            """
            INSERT INTO action_types (name) VALUES (%s)
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            (type_name,)
        )

        type_id = result['id']
        self._type_cache[type_name] = type_id
        self.backend.commit()
        return type_id

    def _get_current_timestamp(self) -> int:
        """Get current Unix timestamp"""
        import time
        return int(time.time())

    def vacuum(self) -> None:
        """Optimize database (VACUUM ANALYZE)"""
        # PostgreSQL VACUUM can't run in transaction - need autocommit
        self.backend.conn.commit()

        old_autocommit = self.backend.conn.autocommit
        self.backend.conn.autocommit = True
        try:
            cursor = self.backend.conn.cursor()
            cursor.execute("VACUUM ANALYZE")
            cursor.close()
            logger.info("✅ Database optimized (PostgreSQL)")
        finally:
            self.backend.conn.autocommit = old_autocommit

    def close(self) -> None:
        """Close database connection"""
        if self.backend:
            self.backend.disconnect()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
        return False

    # ========== Direct Backend Access ==========
    # These methods expose backend functionality for managers

    def execute(self, query: str, params=None):
        """Execute query through backend"""
        return self.backend.execute(query, params)

    def fetchone(self, query: str, params=None):
        """Fetch one row through backend"""
        return self.backend.fetchone(query, params)

    def fetchall(self, query: str, params=None):
        """Fetch all rows through backend"""
        return self.backend.fetchall(query, params)

    def commit(self):
        """Commit transaction"""
        self.backend.commit()

    def rollback(self):
        """Rollback transaction"""
        self.backend.rollback()
