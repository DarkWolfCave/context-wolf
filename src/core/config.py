"""
Configuration Management for ContextWolf
Handles database backend selection and PostgreSQL configuration.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional


class Config:
    """
    Configuration manager for PostgreSQL backend.

    Search order for config files (first match wins):
    1. Environment variables (POSTGRES_*)
    2. YAML config: ~/.context/config.yaml
    3. Legacy JSON: ./cm_keywords.json, ~/.context/cm_keywords.json
    4. Defaults: localhost:5432/context_manager
    """

    DEFAULT_SESSION_TIMEOUT = 3600
    DEFAULT_TOKEN_LIMIT = 200000

    def __init__(self, package_root: Path = None):
        """
        Initialize configuration.

        Args:
            package_root: Root directory of the package (optional)
        """
        self.package_root = package_root or Path(__file__).parent.parent.parent
        self.custom_keywords: Dict[str, Any] = {}

        # Database configuration - PostgreSQL only
        self.database_backend: str = 'postgres'

        # PostgreSQL configuration
        self.postgres_host: str = 'localhost'
        self.postgres_port: int = 5432
        self.postgres_database: str = 'context_manager'
        self.postgres_user: str = os.getenv('USER', 'postgres')
        self.postgres_password: Optional[str] = None
        self.postgres_min_connections: int = 2
        self.postgres_max_connections: int = 10
        self.postgres_connect_timeout: int = 10

        # Load all config sources
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from all available sources"""
        # 1. Try YAML config (new format)
        yaml_loaded = self._load_yaml_config()

        # 2. Load environment variables (override YAML)
        self._load_env_config()

        # 3. Load legacy keywords config (if no YAML)
        if not yaml_loaded:
            self._load_keywords()

    def _load_yaml_config(self) -> bool:
        """
        Load configuration from YAML file.

        Returns:
            True if YAML config was loaded, False otherwise
        """
        config_paths = [
            Path.home() / '.context' / 'config.yaml',
            Path.home() / '.context' / 'postgres_config.yaml',  # Legacy POC name
        ]

        for config_path in config_paths:
            if config_path.exists():
                try:
                    import yaml
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f)

                    if config and 'database' in config:
                        db_config = config['database']

                        # Backend selection (PostgreSQL only)
                        self.database_backend = db_config.get('backend', 'postgres')

                        # PostgreSQL config
                        if 'postgres' in db_config or 'postgresql' in db_config:
                            pg_config = db_config.get('postgres', db_config.get('postgresql', {}))
                            self.postgres_host = pg_config.get('host', self.postgres_host)
                            self.postgres_port = pg_config.get('port', self.postgres_port)
                            self.postgres_database = pg_config.get('database', self.postgres_database)
                            self.postgres_user = pg_config.get('user', self.postgres_user)
                            self.postgres_password = pg_config.get('password')
                            self.postgres_min_connections = pg_config.get('min_connections', self.postgres_min_connections)
                            self.postgres_max_connections = pg_config.get('max_connections', self.postgres_max_connections)
                            self.postgres_connect_timeout = pg_config.get('connect_timeout', self.postgres_connect_timeout)

                        return True

                except ImportError:
                    # PyYAML not installed but config.yaml exists - this is a critical error!
                    # Silent fallback to defaults caused data loss before (wrote to wrong DB).
                    import sys
                    print(
                        f"❌ CRITICAL: Config file found at {config_path} but PyYAML is not installed!\n"
                        f"   Cannot read database configuration - refusing to start with wrong defaults.\n"
                        f"   Fix: pip install PyYAML",
                        file=sys.stderr
                    )
                    raise ImportError(
                        f"PyYAML required to read {config_path}. "
                        f"Install with: pip install PyYAML"
                    )
                except Exception as e:
                    # Config file invalid - this is also critical, don't silently continue
                    import logging
                    logging.error(f"❌ Failed to load config from {config_path}: {e}")
                    raise

        return False

    def _load_env_config(self) -> None:
        """Load configuration from environment variables"""
        # Backend selection (PostgreSQL only)
        if 'DATABASE_BACKEND' in os.environ:
            backend = os.environ['DATABASE_BACKEND'].lower()
            if backend not in ('postgres', 'postgresql'):
                import logging
                logging.warning(f"Unsupported backend '{backend}'. Using PostgreSQL.")
            self.database_backend = 'postgres'

        # PostgreSQL
        if 'POSTGRES_HOST' in os.environ:
            self.postgres_host = os.environ['POSTGRES_HOST']

        if 'POSTGRES_PORT' in os.environ:
            self.postgres_port = int(os.environ['POSTGRES_PORT'])

        if 'POSTGRES_DATABASE' in os.environ:
            self.postgres_database = os.environ['POSTGRES_DATABASE']

        if 'POSTGRES_USER' in os.environ:
            self.postgres_user = os.environ['POSTGRES_USER']

        if 'POSTGRES_PASSWORD' in os.environ:
            self.postgres_password = os.environ['POSTGRES_PASSWORD']

    def _load_keywords(self) -> None:
        """Load keyword configuration from available sources (legacy)"""
        config_paths = [
            Path.cwd() / 'cm_keywords.json',
            self.package_root / 'config' / 'cm_keywords.json',
            Path.home() / '.context' / 'cm_keywords.json'
        ]

        for config_path in config_paths:
            if config_path.exists():
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        self.custom_keywords = json.load(f)
                    break
                except (json.JSONDecodeError, IOError):
                    continue

    def get_keywords(self) -> Dict[str, Any]:
        """Get loaded custom keywords"""
        return self.custom_keywords

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        return self.custom_keywords.get(key, default)

    @staticmethod
    def get_db_path(custom_path: str = None) -> Path:
        """
        Get database path with fallback to default.

        Args:
            custom_path: Custom database path (optional)

        Returns:
            Path to database file
        """
        if custom_path:
            path = Path(custom_path)
        else:
            path = Path.home() / '.context' / 'global.db'

        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def get_project_name() -> str:
        """
        Detect project name from Git root or current directory.

        Priority:
        1. Git repository root name (if in a git repo)
        2. Current directory name
        3. 'default' if in home directory

        Returns:
            Project name (git root name, directory name, or 'default')
        """
        import subprocess

        cwd = Path.cwd()

        if cwd == Path.home():
            return 'default'

        # Try to get git root
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--show-toplevel'],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                git_root = Path(result.stdout.strip())
                return git_root.name
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

        # Fallback to current directory name
        return cwd.name

    def get_backend_info(self) -> str:
        """Get human-readable backend information"""
        return f"PostgreSQL ({self.postgres_host}:{self.postgres_port}/{self.postgres_database})"
