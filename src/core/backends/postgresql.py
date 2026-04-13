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

    def setup_schema(self) -> None:
        """Create PostgreSQL schema - FULL schema from migration"""
        # This will use the COMPLETE_postgres_schema.sql content
        # For now, basic schema to get started

        # Projects table
        self.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                path TEXT,
                created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
                last_active BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT
            )
        """)

        # Action types table
        self.execute("""
            CREATE TABLE IF NOT EXISTS action_types (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL
            )
        """)

        # Insert default types (using INSERT ... ON CONFLICT)
        for type_name in ['code', 'decision', 'fix', 'command', 'docs', 'general', 'todo', 'test', 'feature', 'refactor']:
            self.execute(
                """
                INSERT INTO action_types (name) VALUES (%s)
                ON CONFLICT (name) DO NOTHING
                """,
                (type_name,)
            )

        # Actions table
        self.execute("""
            CREATE TABLE IF NOT EXISTS actions (
                id SERIAL PRIMARY KEY,
                timestamp BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
                type_id INTEGER NOT NULL,
                project_id INTEGER NOT NULL,
                session_id TEXT NOT NULL,
                summary TEXT,
                tokens_used INTEGER DEFAULT 0,
                importance INTEGER DEFAULT 5,
                metadata TEXT,
                FOREIGN KEY (type_id) REFERENCES action_types(id),
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)

        # Action content table
        self.execute("""
            CREATE TABLE IF NOT EXISTS action_content (
                action_id INTEGER PRIMARY KEY,
                content TEXT,
                content_compressed BYTEA,  -- BYTEA instead of BLOB
                content_hash TEXT,
                FOREIGN KEY (action_id) REFERENCES actions(id) ON DELETE CASCADE
            )
        """)

        # Action metadata table
        self.execute("""
            CREATE TABLE IF NOT EXISTS action_metadata (
                action_id INTEGER PRIMARY KEY,
                files TEXT,
                keywords TEXT,
                custom TEXT,
                FOREIGN KEY (action_id) REFERENCES actions(id) ON DELETE CASCADE
            )
        """)

        # Infrastructure hosts table
        self.execute("""
            CREATE TABLE IF NOT EXISTS infra_hosts (
                id SERIAL PRIMARY KEY,
                hostname TEXT UNIQUE NOT NULL,
                ip TEXT,
                port INTEGER DEFAULT 22,
                "user" TEXT,
                identity_file TEXT,
                location TEXT CHECK (location IN ('local', 'extern') OR location IS NULL),
                provider TEXT,
                server_type TEXT,
                scope TEXT DEFAULT 'project' CHECK (scope IN ('global', 'project')),
                project_id INTEGER,
                tags TEXT,
                comment TEXT,
                created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
                updated_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)

        # Infrastructure services table
        self.execute("""
            CREATE TABLE IF NOT EXISTS infra_services (
                id SERIAL PRIMARY KEY,
                host_id INTEGER NOT NULL,
                service_name TEXT NOT NULL,
                env TEXT CHECK (env IN ('prod', 'staging', 'dev', 'test') OR env IS NULL),
                app_path TEXT,
                service_type TEXT,
                deploy_method TEXT,
                health_url TEXT,
                scope TEXT DEFAULT 'project' CHECK (scope IN ('global', 'project')),
                project_id INTEGER,
                tags TEXT,
                comment TEXT,
                created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
                updated_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
                FOREIGN KEY (host_id) REFERENCES infra_hosts(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE(host_id, service_name)
            )
        """)

        # Indexes
        self.execute("CREATE INDEX IF NOT EXISTS idx_actions_project_time ON actions(project_id, timestamp DESC)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_actions_type_time ON actions(type_id, timestamp DESC)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_actions_session ON actions(session_id)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_actions_timestamp ON actions(timestamp DESC)")

        # Infrastructure indexes
        self.execute("CREATE INDEX IF NOT EXISTS idx_infra_hosts_scope ON infra_hosts(scope)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_infra_hosts_location ON infra_hosts(location)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_infra_hosts_project ON infra_hosts(project_id)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_infra_services_scope ON infra_services(scope)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_infra_services_env ON infra_services(env)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_infra_services_host ON infra_services(host_id)")

        self.commit()
        logger.info("✅ PostgreSQL schema created (with infrastructure tables)")

    def setup_fts(self) -> None:
        """Setup PostgreSQL full-text search with tsvector"""
        # Add tsvector column for actions
        try:
            self.execute("""
                ALTER TABLE actions
                ADD COLUMN IF NOT EXISTS search_vector tsvector
            """)
        except Exception as e:
            logger.debug(f"search_vector column: {e}")

        # Create GIN index for fast full-text search
        self.execute("""
            CREATE INDEX IF NOT EXISTS actions_search_idx
            ON actions USING GIN(search_vector)
        """)

        # Create trigger to auto-update search_vector
        self.execute("""
            CREATE OR REPLACE FUNCTION actions_search_trigger() RETURNS trigger AS $$
            BEGIN
                NEW.search_vector :=
                    setweight(to_tsvector('english', coalesce(NEW.summary, '')), 'A') ||
                    setweight(to_tsvector('english', coalesce(NEW.metadata, '')), 'B');
                RETURN NEW;
            END
            $$ LANGUAGE plpgsql
        """)

        # Drop trigger if exists (to avoid duplicates)
        self.execute("DROP TRIGGER IF EXISTS actions_search_update ON actions")

        # Create trigger
        self.execute("""
            CREATE TRIGGER actions_search_update
            BEFORE INSERT OR UPDATE ON actions
            FOR EACH ROW EXECUTE FUNCTION actions_search_trigger()
        """)

        # Update existing rows
        self.execute("""
            UPDATE actions
            SET search_vector =
                setweight(to_tsvector('english', coalesce(summary, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(metadata, '')), 'B')
            WHERE search_vector IS NULL
        """)

        self.commit()
        logger.info("✅ PostgreSQL FTS (tsvector) configured for actions")

        # Add search_vector for snippets (if table exists)
        try:
            self.execute("ALTER TABLE snippets ADD COLUMN IF NOT EXISTS search_vector tsvector")
            self.execute("CREATE INDEX IF NOT EXISTS snippets_search_idx ON snippets USING GIN(search_vector)")

            self.execute("""
                CREATE OR REPLACE FUNCTION snippets_search_trigger() RETURNS trigger AS $$
                BEGIN
                    NEW.search_vector := to_tsvector('english',
                        coalesce(NEW.name, '') || ' ' ||
                        coalesce(NEW.description, '') || ' ' ||
                        coalesce(NEW.tags, '')
                    );
                    RETURN NEW;
                END
                $$ LANGUAGE plpgsql
            """)

            self.execute("DROP TRIGGER IF EXISTS snippets_search_update ON snippets")
            self.execute("""
                CREATE TRIGGER snippets_search_update
                BEFORE INSERT OR UPDATE ON snippets
                FOR EACH ROW EXECUTE FUNCTION snippets_search_trigger()
            """)

            self.commit()
            logger.info("✅ PostgreSQL FTS configured for snippets")
        except Exception as e:
            logger.debug(f"Snippets FTS setup: {e}")

        # Add search_vector for ai_instructions (if table exists)
        try:
            self.execute("ALTER TABLE ai_instructions ADD COLUMN IF NOT EXISTS search_vector tsvector")
            self.execute("CREATE INDEX IF NOT EXISTS ai_instructions_search_idx ON ai_instructions USING GIN(search_vector)")

            self.execute("""
                CREATE OR REPLACE FUNCTION ai_instructions_search_trigger() RETURNS trigger AS $$
                BEGIN
                    NEW.search_vector := to_tsvector('english',
                        coalesce(NEW.instruction, '') || ' ' ||
                        coalesce(NEW.category, '')
                    );
                    RETURN NEW;
                END
                $$ LANGUAGE plpgsql
            """)

            self.execute("DROP TRIGGER IF EXISTS ai_instructions_search_update ON ai_instructions")
            self.execute("""
                CREATE TRIGGER ai_instructions_search_update
                BEFORE INSERT OR UPDATE ON ai_instructions
                FOR EACH ROW EXECUTE FUNCTION ai_instructions_search_trigger()
            """)

            self.commit()
            logger.info("✅ PostgreSQL FTS configured for ai_instructions")
        except Exception as e:
            logger.debug(f"AI instructions FTS setup: {e}")
