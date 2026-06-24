"""
Simple schema migration system for Context Manager.

Tracks applied migrations in a `schema_migrations` table.
Runs pending .sql files from migrations/ in numeric order.
Existing databases get migration 001 marked as applied automatically.
"""

import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"


def ensure_migration_table(backend) -> None:
    """Create schema_migrations table if it doesn't exist."""
    backend.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT NOW()
        )
    """)


def get_applied_migrations(backend) -> List[str]:
    """Get list of already applied migration versions."""
    try:
        rows = backend.fetchall("SELECT version FROM schema_migrations ORDER BY version")
        return [row['version'] for row in rows]
    except Exception:
        return []


def get_pending_migrations(backend) -> List[Path]:
    """Get migration files that haven't been applied yet."""
    applied = get_applied_migrations(backend)

    migration_files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))
    pending = []
    for f in migration_files:
        version = f.stem  # e.g. "001_initial_schema"
        if version not in applied:
            pending.append(f)

    return pending


def is_existing_database(backend) -> bool:
    """Check if this is an existing database (has data) vs fresh install."""
    try:
        result = backend.fetchone(
            "SELECT count(*) as c FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'actions'"
        )
        return result and result['c'] > 0
    except Exception:
        return False


def run_migrations(backend) -> int:
    """
    Run all pending migrations.

    For existing databases (pre-V5), marks migration 001 as applied
    since those tables already exist.

    Returns:
        Number of migrations applied
    """
    ensure_migration_table(backend)

    # If this is an existing database but has no migration records,
    # mark 001 as already applied (those tables already exist on a pre-migrator database)
    applied = get_applied_migrations(backend)
    if not applied and is_existing_database(backend):
        logger.info("📋 Existing database detected - marking migration 001 as applied")
        backend.execute(
            "INSERT INTO schema_migrations (version) VALUES (%s) ON CONFLICT DO NOTHING",
            ("001_initial_schema",)
        )

    pending = get_pending_migrations(backend)
    if not pending:
        logger.debug("✅ Database schema is up to date")
        return 0

    applied_count = 0
    for migration_file in pending:
        version = migration_file.stem
        logger.info(f"🔄 Applying migration: {version}")

        sql = migration_file.read_text()

        # Split on semicolons but handle $$ blocks (PL/pgSQL functions)
        _execute_migration_sql(backend, sql)

        backend.execute(
            "INSERT INTO schema_migrations (version) VALUES (%s)",
            (version,)
        )
        applied_count += 1
        logger.info(f"✅ Migration applied: {version}")

    return applied_count


def _execute_migration_sql(backend, sql: str) -> None:
    """
    Execute a migration SQL file.

    Handles $$ delimited PL/pgSQL blocks correctly by executing
    the entire file as one statement batch.
    """
    # PostgreSQL can handle the entire file as a single execution
    # if we use the raw cursor (bypasses SmartCursor placeholder conversion)
    try:
        backend.cursor.execute(sql)
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise
