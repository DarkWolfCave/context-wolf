"""
Abstract Database Backend Interface
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class DatabaseBackend(ABC):
    """
    Abstract base class for database backends.
    """

    @abstractmethod
    def connect(self) -> None:
        """Establish database connection"""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close database connection"""
        pass

    @abstractmethod
    def execute(self, query: str, params: Optional[Tuple] = None) -> Any:
        """Execute a query with parameters."""
        pass

    @abstractmethod
    def fetchone(self, query: str, params: Optional[Tuple] = None) -> Optional[Dict]:
        """Execute query and fetch one row."""
        pass

    @abstractmethod
    def fetchall(self, query: str, params: Optional[Tuple] = None) -> List[Dict]:
        """Execute query and fetch all rows."""
        pass

    @abstractmethod
    def commit(self) -> None:
        """Commit current transaction"""
        pass

    @abstractmethod
    def rollback(self) -> None:
        """Rollback current transaction"""
        pass

    def get_placeholder(self) -> str:
        """Get parameter placeholder (%s for PostgreSQL)."""
        return '%s'

    @abstractmethod
    def full_text_search(self, table: str, query: str, columns: List[str]) -> List[Dict]:
        """Perform full-text search on specified table."""
        pass

    def convert_placeholders(self, query: str) -> str:
        """Convert '?' placeholders to '%s' for PostgreSQL."""
        return query.replace('?', '%s')


class BackendFactory:
    """
    Factory to create PostgreSQL backend instances.

    Usage:
        from src.core.config import Config
        config = Config()
        backend = BackendFactory.create(config)
        backend.connect()
    """

    @staticmethod
    def create(config) -> DatabaseBackend:
        """
        Create PostgreSQL backend from configuration.

        Args:
            config: Config object with PostgreSQL settings

        Returns:
            PostgreSQLBackend instance
        """
        from .postgresql import PostgreSQLBackend

        return PostgreSQLBackend(
            host=getattr(config, 'postgres_host', 'localhost'),
            port=getattr(config, 'postgres_port', 5432),
            database=getattr(config, 'postgres_database', 'context_manager'),
            user=getattr(config, 'postgres_user', 'cm_user'),
            password=getattr(config, 'postgres_password', None),
            min_connections=getattr(config, 'postgres_min_connections', 2),
            max_connections=getattr(config, 'postgres_max_connections', 10),
            connect_timeout=getattr(config, 'postgres_connect_timeout', 10)
        )
