"""
PostgreSQL Database Backend Implementation
Handles PostgreSQL-specific operations with tsvector full-text search.
"""

from typing import Any, Dict, List, Optional, Tuple
import logging

from .base import DatabaseBackend

logger = logging.getLogger(__name__)


class PostgreSQLBackend(DatabaseBackend):
    """PostgreSQL database backend implementation with tsvector FTS support"""

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        min_connections: int = 2,
        max_connections: int = 10,
        connect_timeout: int = 10
    ):
        """
        Initialize PostgreSQL backend.

        Args:
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            min_connections: Minimum pool connections
            max_connections: Maximum pool connections
            connect_timeout: Connection timeout in seconds
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.connect_timeout = connect_timeout
        self.conn = None
        self.cursor = None

    def connect(self) -> None:
        """Establish PostgreSQL connection"""
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor

            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                connect_timeout=self.connect_timeout,
                cursor_factory=RealDictCursor,  # Set as default for ALL cursors!
                # TCP Keepalive settings to prevent connection drops
                keepalives=1,           # Enable keepalives
                keepalives_idle=60,     # Seconds before sending first keepalive
                keepalives_interval=10, # Seconds between keepalives
                keepalives_count=5      # Number of keepalives before giving up
            )

            # CRITICAL FIX for MCP servers: Enable autocommit mode to prevent
            # "idle in transaction" timeouts that cause "cursor already closed" errors.
            # MCP tools can take minutes to execute, causing PostgreSQL to kill connections
            # that sit idle in a transaction for too long (idle_in_transaction_session_timeout).
            # With autocommit, each query commits immediately, preventing idle transactions.
            self.conn.autocommit = True
            logger.info("✅ PostgreSQL autocommit enabled (prevents idle transaction timeouts)")

            # Create initial cursor
            self.cursor = self.conn.cursor()

            logger.info(f"✅ PostgreSQL connected: {self.host}:{self.port}/{self.database}")

        except ImportError:
            raise ImportError(
                "psycopg2 not installed. Run: pip install psycopg2-binary"
            )
        except Exception as e:
            logger.error(f"❌ PostgreSQL connection failed: {e}")
            raise

    def disconnect(self) -> None:
        """Close PostgreSQL connection"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
            logger.info("PostgreSQL connection closed")

    def _ensure_connection(self) -> None:
        """Ensure database connection is alive, reconnect if needed"""
        try:
            # Quick check if connection is closed
            if self.conn is None or self.conn.closed:
                logger.warning("🔄 Connection lost, reconnecting...")
                self.connect()
                return

            # Try a simple query to verify connection
            self.cursor.execute("SELECT 1")
            self.cursor.fetchone()
        except Exception as e:
            logger.warning(f"🔄 Connection check failed ({e}), reconnecting...")
            try:
                self.disconnect()
            except Exception:
                pass
            self.connect()

    def execute(self, query: str, params: Optional[Tuple] = None) -> Any:
        """Execute PostgreSQL query with auto-reconnect"""
        # Convert ? to %s
        query = self.convert_placeholders(query)

        try:
            if params:
                return self.cursor.execute(query, params)
            return self.cursor.execute(query)
        except Exception as e:
            # Check if it's a connection error
            error_str = str(e).lower()
            if 'connection' in error_str or 'closed' in error_str or 'server' in error_str:
                logger.warning(f"🔄 Query failed with connection error, reconnecting: {e}")
                self._ensure_connection()
                # Retry once
                if params:
                    return self.cursor.execute(query, params)
                return self.cursor.execute(query)
            raise

    def fetchone(self, query: str, params: Optional[Tuple] = None) -> Optional[Dict]:
        """Fetch one row from PostgreSQL"""
        self.execute(query, params)
        row = self.cursor.fetchone()
        if row:
            return dict(row)
        return None

    def fetchall(self, query: str, params: Optional[Tuple] = None) -> List[Dict]:
        """Fetch all rows from PostgreSQL"""
        self.execute(query, params)
        rows = self.cursor.fetchall()
        return [dict(row) for row in rows]

    def commit(self) -> None:
        """Commit PostgreSQL transaction"""
        if self.conn:
            self.conn.commit()

    def rollback(self) -> None:
        """Rollback PostgreSQL transaction"""
        if self.conn:
            self.conn.rollback()

    def get_placeholder(self) -> str:
        """PostgreSQL uses '%s' placeholders"""
        return '%s'

    def full_text_search(self, table: str, query: str, columns: List[str]) -> List[Dict]:
        """
        Perform tsvector full-text search on PostgreSQL.

        Args:
            table: Table name (e.g., 'actions')
            query: Search query
            columns: Not used (search_vector column is used)

        Returns:
            List of matching rows
        """
        # PostgreSQL uses search_vector column with @@ operator
        # plainto_tsquery handles multi-word queries automatically (converts to AND)
        sql = f"""
            SELECT * FROM {table}
            WHERE search_vector @@ plainto_tsquery('english', %s)
            ORDER BY ts_rank(search_vector, plainto_tsquery('english', %s)) DESC
        """

        return self.fetchall(sql, (query, query))
