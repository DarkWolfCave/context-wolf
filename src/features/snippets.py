"""
Snippet Management - Code Templates and Examples
Handles adding, searching, and managing code snippets.

Architecture: Features Layer (depends on Core + Domain)
"""

import json
import hashlib
import zlib
import re
from pathlib import Path
from typing import List, Dict, Optional

from ..core.database import Database


class SnippetManager:
    """
    Manages code snippets and templates.

    Responsibilities:
    - Add snippets from files
    - Search snippets with full-text search
    - Analyze code structure (functions, classes, targets)
    - Track usage statistics
    - Store/compress full content

    Dependencies:
    - Database (core layer)
    """

    FILE_TYPE_MAP = {
        '.py': 'python',
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.sh': 'shell',
        '.bash': 'shell',
        '.zsh': 'shell',
        '.yml': 'yaml',
        '.yaml': 'yaml',
        '.json': 'json',
        '.xml': 'xml',
        '.html': 'html',
        '.htm': 'html',
        '.css': 'css',
        '.scss': 'css',
        '.sql': 'sql',
        '.rb': 'ruby',
        '.go': 'go',
        '.rs': 'rust',
        '.java': 'java',
        '.php': 'php',
        '.c': 'c',
        '.cpp': 'cpp',
        '.h': 'header',
        '.hpp': 'header',
        '.vue': 'vue',
        '.svelte': 'svelte',
        '.toml': 'toml',
        '.ini': 'ini',
        '.env': 'env',
        '.graphql': 'graphql',
        '.gql': 'graphql',
        '.proto': 'proto',
        '.swift': 'swift',
        '.kt': 'kotlin',
        '.scala': 'scala',
        '.lua': 'lua',
        '.pl': 'perl',
        '.r': 'r',
        '.hs': 'haskell',
        '.ex': 'elixir',
        '.exs': 'elixir',
        '.clj': 'clojure',
        '.dart': 'dart',
        '.zig': 'zig',
        '.nim': 'nim',
    }

    def __init__(self, database: Database):
        """
        Initialize SnippetManager.

        Args:
            database: Database instance
        """
        self.db = database
        self.conn = database.conn

    def add(
        self,
        file_path: str,
        name: str = None,
        description: str = None,
        tags: List[str] = None,
        store_content: bool = False
    ) -> int:
        """
        Add a code snippet/template to database.

        Args:
            file_path: Path to file
            name: Snippet name (default: filename without extension)
            description: Description of snippet
            tags: List of tags
            store_content: Store full content in DB (default: False)

        Returns:
            Snippet ID

        Raises:
            FileNotFoundError: If file doesn't exist

        Features:
        - Auto-detects file type
        - Extracts key sections (functions, classes, targets)
        - Compresses content if >1KB
        - Updates existing snippets if changed
        """
        file_path = Path(file_path).resolve()

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not name:
            name = file_path.stem

        file_stat = file_path.stat()
        file_size = file_stat.st_size
        last_modified = int(file_stat.st_mtime)

        try:
            content = file_path.read_text(encoding='utf-8')
            line_count = len(content.splitlines())
        except Exception as e:
            print(f"Warning: Could not read file as text: {e}")
            content = ""
            line_count = 0

        md5_hash = hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()

        file_type = self._detect_file_type(file_path)

        extract_lines = content.splitlines()[:50]
        extract = '\n'.join(extract_lines)
        if len(extract) > 2048:
            extract = extract[:2048] + '...'

        key_sections = self._analyze_key_sections(content, file_type)

        cursor = self.conn.cursor()

        cursor.execute("SELECT id, md5_hash FROM snippets WHERE name = %s", (name,))
        existing = cursor.fetchone()

        if existing:
            if existing['md5_hash'] == md5_hash:
                print(f"⚠️ Snippet '{name}' already exists with same content")
                return existing['id']
            else:
                cursor.execute("""
                    UPDATE snippets SET
                        file_path = %s, description = %s, file_type = %s,
                        file_size = %s, line_count = %s, tags = %s,
                        key_sections = %s, extract = %s, md5_hash = %s,
                        last_modified = %s
                    WHERE id = %s
                """, (
                    str(file_path), description, file_type, file_size,
                    line_count, json.dumps(tags) if tags else None,
                    json.dumps(key_sections), extract, md5_hash,
                    last_modified, existing['id']
                ))
                snippet_id = existing['id']
                print(f"✅ Updated snippet '{name}'")
        else:
            cursor.execute("""
                INSERT INTO snippets (
                    name, file_path, description, file_type, file_size,
                    line_count, tags, key_sections, extract, md5_hash,
                    last_modified, project_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                name, str(file_path), description, file_type, file_size,
                line_count, json.dumps(tags) if tags else None,
                json.dumps(key_sections), extract, md5_hash,
                last_modified, self.db.get_or_create_project(Path.cwd().name)
            ))
            snippet_id = cursor.fetchone()['id']

            print(f"✅ Added snippet '{name}'")

        if store_content and content:
            compressed = zlib.compress(content.encode()) if len(content) > 1024 else None

            cursor.execute("""
                INSERT INTO snippet_content (snippet_id, content, content_compressed)
                VALUES (%s, %s, %s)
                ON CONFLICT (snippet_id) DO UPDATE SET
                    content = EXCLUDED.content,
                    content_compressed = EXCLUDED.content_compressed
            """, (snippet_id, content if not compressed else None, compressed))

        self.conn.commit()
        return snippet_id

    def _detect_file_type(self, file_path: Path) -> str:
        """
        Detect file type from extension or filename.

        Args:
            file_path: Path to file

        Returns:
            File type string
        """
        suffix = file_path.suffix.lower()
        file_type = self.FILE_TYPE_MAP.get(suffix, 'text')

        if file_path.name.lower() in ['makefile', 'gnumakefile']:
            file_type = 'makefile'
        elif file_path.name.lower() == 'dockerfile':
            file_type = 'dockerfile'
        elif file_path.name.lower().startswith('docker-compose'):
            file_type = 'docker-compose'

        return file_type

    def _analyze_key_sections(self, content: str, file_type: str) -> Dict:
        """
        Analyze and extract key sections from code.

        Args:
            content: File content
            file_type: Type of file

        Returns:
            Dict mapping section names to line numbers

        Supports:
        - Makefile: targets
        - Python: classes and functions
        - Shell: functions
        - YAML: top-level keys
        """
        sections = {}
        lines = content.splitlines()

        if file_type == 'makefile':
            for i, line in enumerate(lines, 1):
                if match := re.match(r'^([a-zA-Z_\-]+):', line):
                    target = match.group(1)
                    if target not in ['PHONY', 'SILENT']:
                        sections[target] = f"line {i}"

        elif file_type == 'python':
            for i, line in enumerate(lines, 1):
                if match := re.match(r'^(class|def)\s+(\w+)', line):
                    sections[match.group(2)] = f"line {i}"

        elif file_type in ['shell', 'bash', 'zsh']:
            for i, line in enumerate(lines, 1):
                if match := re.match(r'^(\w+)\(\)\s*{', line):
                    sections[match.group(1)] = f"line {i}"
                elif match := re.match(r'^function\s+(\w+)', line):
                    sections[match.group(1)] = f"line {i}"

        elif file_type in ['yaml', 'docker-compose']:
            for i, line in enumerate(lines, 1):
                if match := re.match(r'^([a-zA-Z_\-]+):', line):
                    sections[match.group(1)] = f"line {i}"

        return sections

    def search(
        self,
        query: str = None,
        file_type: str = None,
        tags: List[str] = None,
        limit: int = 20
    ) -> List[Dict]:
        """
        Search snippets with filters.

        Args:
            query: Full-text search query
            file_type: Filter by file type
            tags: Filter by tags
            limit: Maximum results

        Returns:
            List of matching snippets

        Search order: usage_count DESC, last_modified DESC
        """
        cursor = self.conn.cursor()

        where_clauses = []
        params = []

        if query:
            where_clauses.append("""
                search_vector @@ plainto_tsquery('english', %s)
            """)
            params.append(query)

        if file_type:
            where_clauses.append("s.file_type = %s")
            params.append(file_type)

        if tags:
            for tag in tags:
                where_clauses.append("s.tags LIKE %s")
                params.append(f'%"{tag}"%')

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        sql = f"""
            SELECT
                s.id, s.name, s.file_path, s.description,
                s.file_type, s.file_size, s.line_count,
                s.tags, s.key_sections, s.extract,
                s.usage_count, s.last_used, s.last_modified,
                p.name as project
            FROM snippets s
            LEFT JOIN projects p ON s.project_id = p.id
            WHERE {where_sql}
            ORDER BY s.usage_count DESC, s.last_modified DESC
            LIMIT %s
        """

        params.append(limit)
        results = []

        for row in cursor.execute(sql, params):
            result = dict(row)
            if result['tags']:
                result['tags'] = json.loads(result['tags'])
            if result['key_sections']:
                result['key_sections'] = json.loads(result['key_sections'])
            results.append(result)

        return results

    def get(self, name: str, full_content: bool = False) -> Optional[Dict]:
        """
        Get a specific snippet by name.

        Args:
            name: Snippet name
            full_content: Include full file content

        Returns:
            Snippet dict or None if not found

        Side effect: Increments usage_count
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT
                s.*, p.name as project,
                sc.content, sc.content_compressed
            FROM snippets s
            LEFT JOIN projects p ON s.project_id = p.id
            LEFT JOIN snippet_content sc ON s.id = sc.snippet_id
            WHERE s.name = %s
        """, (name,))

        row = cursor.fetchone()
        if not row:
            return None

        cursor.execute("""
            UPDATE snippets SET
                usage_count = usage_count + 1,
                last_used = EXTRACT(epoch FROM now())::bigint
            WHERE name = %s
        """, (name,))
        self.conn.commit()

        result = dict(row)

        if result['tags']:
            result['tags'] = json.loads(result['tags'])
        if result['key_sections']:
            result['key_sections'] = json.loads(result['key_sections'])

        if full_content:
            if result['content_compressed']:
                result['content'] = zlib.decompress(result['content_compressed']).decode()
            elif not result['content']:
                try:
                    result['content'] = Path(result['file_path']).read_text()
                except Exception:
                    result['content'] = None

        return result

    def get_by_id(self, snippet_id: int, full_content: bool = False) -> Optional[Dict]:
        """
        Get a specific snippet by ID.

        Args:
            snippet_id: Snippet ID
            full_content: Include full file content

        Returns:
            Snippet dict or None if not found

        Side effect: Increments usage_count
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT
                s.*, p.name as project,
                sc.content, sc.content_compressed
            FROM snippets s
            LEFT JOIN projects p ON s.project_id = p.id
            LEFT JOIN snippet_content sc ON s.id = sc.snippet_id
            WHERE s.id = %s
        """, (snippet_id,))

        row = cursor.fetchone()
        if not row:
            return None

        cursor.execute("""
            UPDATE snippets SET
                usage_count = usage_count + 1,
                last_used = EXTRACT(epoch FROM now())::bigint
            WHERE id = %s
        """, (snippet_id,))
        self.conn.commit()

        result = dict(row)

        if result['tags']:
            result['tags'] = json.loads(result['tags'])
        if result['key_sections']:
            result['key_sections'] = json.loads(result['key_sections'])

        if full_content:
            if result['content_compressed']:
                result['content'] = zlib.decompress(result['content_compressed']).decode()
            elif not result['content']:
                try:
                    result['content'] = Path(result['file_path']).read_text()
                except Exception:
                    result['content'] = None

        return result

    def list_all(self, limit: int = 100) -> List[Dict]:
        """
        List all snippets.

        Args:
            limit: Maximum results

        Returns:
            List of all snippets
        """
        return self.search(limit=limit)

    def delete(self, name: str) -> bool:
        """
        Delete a snippet by name.

        Args:
            name: Snippet name

        Returns:
            True if deleted, False if not found

        Security: Uses parameterized queries
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM snippets WHERE name = %s", (name,))
        self.conn.commit()
        return cursor.rowcount > 0

    def delete_by_id(self, snippet_id: int) -> bool:
        """
        Delete a snippet by ID.

        Args:
            snippet_id: Snippet ID

        Returns:
            True if deleted, False if not found

        Security: Uses parameterized queries
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM snippets WHERE id = %s", (snippet_id,))
        self.conn.commit()
        return cursor.rowcount > 0