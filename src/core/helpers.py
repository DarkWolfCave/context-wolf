"""
Helper Utilities for Context Manager V3
Compression, validation, and common utilities.

Security: Input validation following 2025 best practices
"""

import re
import zlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


class ContentCompressor:
    """
    Handle content compression for large texts.

    Compresses content >1KB to save space.
    Uses zlib with level 6 (balanced compression/speed).
    """

    COMPRESSION_THRESHOLD = 1000

    @staticmethod
    def compress(content: str) -> Tuple[Optional[str], Optional[bytes]]:
        """
        Compress content if it exceeds threshold.

        Args:
            content: Text to potentially compress

        Returns:
            Tuple of (uncompressed_text, compressed_bytes)
            If content < 1KB: (content, None)
            If content >= 1KB: (None, compressed_bytes)
        """
        if len(content) < ContentCompressor.COMPRESSION_THRESHOLD:
            return content, None

        compressed = zlib.compress(content.encode('utf-8'), level=6)
        return None, compressed

    @staticmethod
    def decompress(content: str, compressed: bytes) -> str:
        """
        Decompress content if compressed.

        Args:
            content: Uncompressed text (may be None)
            compressed: Compressed bytes (may be None)

        Returns:
            Decompressed text or original content
        """
        if compressed:
            return zlib.decompress(compressed).decode('utf-8')
        return content or ''


class InputValidator:
    """
    Input validation to prevent injection attacks and ensure data integrity.

    Following 2025 security best practices:
    - Whitelist-based validation
    - Length limits
    - Type checking
    """

    MAX_PROJECT_NAME_LENGTH = 100
    MAX_TYPE_NAME_LENGTH = 50
    MAX_SCOPE_LENGTH = 20
    MAX_PRIORITY_LENGTH = 20

    VALID_SCOPES = frozenset(['global', 'project', 'session'])
    VALID_PRIORITIES = frozenset(['must', 'should', 'nice'])
    VALID_CATEGORIES = frozenset([
        'security', 'style', 'performance', 'architecture',
        'testing', 'documentation', 'debugging', 'general'
    ])

    @staticmethod
    def clean_text(text: str, max_length: int = 1000) -> str:
        """
        Clean and validate general text input.

        Args:
            text: Input text to clean
            max_length: Maximum allowed length

        Returns:
            Cleaned text string
        """
        if not text:
            return ""

        # Remove leading/trailing whitespace
        text = text.strip()

        # Limit length
        if len(text) > max_length:
            text = text[:max_length]

        # Remove null bytes and other control characters
        text = ''.join(char for char in text if ord(char) >= 32 or char == '\n')

        return text

    @staticmethod
    def sanitize_project_name(name: str) -> str:
        """
        Validate and sanitize project names.

        Rules:
        - 1-100 characters
        - Alphanumeric, dash, underscore only
        - No path traversal attempts

        Args:
            name: Project name to validate

        Returns:
            Sanitized project name

        Raises:
            ValueError: If name is invalid
        """
        if not name or not isinstance(name, str):
            raise ValueError("Project name is required")

        name = name.strip()

        if not name or len(name) > InputValidator.MAX_PROJECT_NAME_LENGTH:
            raise ValueError(
                f"Project name must be 1-{InputValidator.MAX_PROJECT_NAME_LENGTH} characters"
            )

        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            raise ValueError(
                "Project name can only contain letters, numbers, dash, and underscore"
            )

        if '..' in name or '/' in name or '\\' in name:
            raise ValueError("Path traversal attempt detected in project name")

        return name

    @staticmethod
    def validate_scope(scope: str) -> str:
        """
        Validate scope values.

        Args:
            scope: Scope to validate

        Returns:
            Validated scope

        Raises:
            ValueError: If scope is invalid
        """
        if not scope or not isinstance(scope, str):
            raise ValueError("Scope is required")

        scope = scope.lower().strip()

        if scope not in InputValidator.VALID_SCOPES:
            raise ValueError(
                f"Scope must be one of: {', '.join(sorted(InputValidator.VALID_SCOPES))}"
            )

        return scope

    @staticmethod
    def validate_priority(priority: str) -> str:
        """
        Validate priority values.

        Args:
            priority: Priority to validate

        Returns:
            Validated priority

        Raises:
            ValueError: If priority is invalid
        """
        if not priority or not isinstance(priority, str):
            raise ValueError("Priority is required")

        priority = priority.lower().strip()

        if priority not in InputValidator.VALID_PRIORITIES:
            raise ValueError(
                f"Priority must be one of: {', '.join(sorted(InputValidator.VALID_PRIORITIES))}"
            )

        return priority

    @staticmethod
    def validate_category(category: str) -> str:
        """
        Validate category values.

        Args:
            category: Category to validate

        Returns:
            Validated category

        Raises:
            ValueError: If category is invalid
        """
        if not category or not isinstance(category, str):
            raise ValueError("Category is required")

        category = category.lower().strip()

        if category not in InputValidator.VALID_CATEGORIES:
            raise ValueError(
                f"Category must be one of: {', '.join(sorted(InputValidator.VALID_CATEGORIES))}"
            )

        return category

    @staticmethod
    def sanitize_type_name(type_name: str) -> str:
        """
        Validate and sanitize action type names.

        Args:
            type_name: Type name to validate

        Returns:
            Sanitized type name

        Raises:
            ValueError: If type name is invalid
        """
        if not type_name or not isinstance(type_name, str):
            raise ValueError("Type name is required")

        type_name = type_name.strip()

        if not type_name or len(type_name) > InputValidator.MAX_TYPE_NAME_LENGTH:
            raise ValueError(
                f"Type name must be 1-{InputValidator.MAX_TYPE_NAME_LENGTH} characters"
            )

        if not re.match(r'^[a-zA-Z0-9_-]+$', type_name):
            raise ValueError(
                "Type name can only contain letters, numbers, dash, and underscore"
            )

        return type_name


class PathValidator:
    """
    Validate file paths to prevent path traversal attacks.

    Security: Prevents '../' attacks and ensures paths are within allowed directories
    """

    @staticmethod
    def validate_file_path(file_path: str, base_dir: Path = None) -> Path:
        """
        Validate and resolve file path.

        Args:
            file_path: Path to validate
            base_dir: Base directory to restrict to (optional)

        Returns:
            Resolved Path object

        Raises:
            ValueError: If path is invalid or attempts traversal

        Security: Uses Path.resolve() to prevent '../' attacks
        """
        if not file_path or not isinstance(file_path, str):
            raise ValueError("File path is required")

        try:
            path = Path(file_path).resolve()
        except (ValueError, OSError) as e:
            raise ValueError(f"Invalid file path: {e}")

        if base_dir:
            base_dir = base_dir.resolve()
            try:
                path.relative_to(base_dir)
            except ValueError:
                raise ValueError(
                    f"Path traversal detected: {file_path} is outside {base_dir}"
                )

        return path

    @staticmethod
    def is_safe_path(file_path: str, allowed_extensions: set = None) -> bool:
        """
        Check if path is safe (no suspicious patterns).

        Args:
            file_path: Path to check
            allowed_extensions: Set of allowed file extensions (optional)

        Returns:
            True if path is safe
        """
        path_str = str(file_path).lower()

        suspicious_patterns = ['../', '..\\', '%2e%2e', '%252e']
        for pattern in suspicious_patterns:
            if pattern in path_str:
                return False

        if allowed_extensions:
            path = Path(file_path)
            if path.suffix.lower() not in allowed_extensions:
                return False

        return True


def format_timestamp(timestamp: int, date_only: bool = False) -> str:
    """
    Format Unix timestamp to human-readable string.

    Args:
        timestamp: Unix timestamp
        date_only: If True, return only date (YYYY-MM-DD)

    Returns:
        Formatted date/time string
    """
    dt = datetime.fromtimestamp(timestamp)
    if date_only:
        return dt.strftime('%Y-%m-%d')
    else:
        return dt.strftime('%Y-%m-%d %H:%M')