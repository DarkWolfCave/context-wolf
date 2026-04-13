"""
Markdown File Indexing
Indexes MD files and extracts important sections and patterns.

Architecture: Features Layer (depends on Core + Domain)
"""

import re
import hashlib
from pathlib import Path
from typing import List, Set, Optional, Tuple

from ..core.database import Database


class IndexingManager:
    """
    Manages MD file indexing and pattern extraction.

    Responsibilities:
    - Index MD files into database
    - Extract important sections by keywords
    - Extract special patterns (commands, scripts, paths)
    - Support custom keyword sets
    - Multi-language keyword support

    Dependencies:
    - Database (core layer)
    - ActionManager (domain layer) - via save callback
    """

    DEFAULT_KEYWORDS = {
        # Deployment & Ops
        'deploy', 'deployment', 'install', 'installation', 'setup', 'production', 'staging',
        # Version & Release
        'version', 'release', 'bump', 'changelog', 'upgrade', 'migration',
        # Commands & Scripts
        'script', 'command', 'usage', 'cli', 'run', 'execute', 'beispiel', 'example',
        # Important markers (multi-lang)
        'important', 'critical', 'warning', 'caution', 'note', 'attention',
        'wichtig', 'achtung', 'hinweis', 'warnung',  # German
        'importante', 'atención', 'aviso',  # Spanish
        'important', 'attention', 'avertissement',  # French
        # Infrastructure
        'docker', 'kubernetes', 'k8s', 'container', 'compose',
        'api', 'endpoint', 'route', 'webhook',
        'database', 'db', 'postgres', 'mysql', 'mongo', 'redis',
        'config', 'configuration', 'env', 'environment', 'settings',
        'path', 'directory', 'folder', 'location',
        # Development
        'test', 'debug', 'troubleshoot', 'error', 'fix',
        'build', 'compile', 'bundle', 'package',
        'ci', 'cd', 'pipeline', 'workflow', 'action'
    }

    SKIP_DIRECTORIES = {
        '.git',
        '.hg',
        '.svn',
        'node_modules',
        'bower_components',
        '.venv',
        'venv',
        'env',
        '.env',
        'dist',
        'build',
        '__pycache__',
        '.mypy_cache',
        '.pytest_cache'
    }

    def __init__(self, database: Database, save_callback, custom_keywords: dict = None):
        """
        Initialize IndexingManager.

        Args:
            database: Database instance
            save_callback: Function to save indexed content (from ActionManager)
            custom_keywords: Optional custom keyword configuration
        """
        self.db = database
        self.conn = database.conn
        self.save_callback = save_callback
        self.custom_keywords = custom_keywords or {}

    def _check_if_needs_reindex(self, file_path: Path, current_hash: str) -> Tuple[bool, Optional[int]]:
        """
        Check if file needs to be re-indexed based on hash.

        Args:
            file_path: Absolute path to file
            current_hash: Current hash of file content

        Returns:
            Tuple of (needs_reindex, existing_action_id)
            - (True, None): File not indexed yet, needs index
            - (True, action_id): File changed, needs update
            - (False, action_id): File unchanged, skip
        """
        cursor = self.conn.cursor()

        # Find existing entry by source_file
        cursor.execute("""
            SELECT a.id, am.source_hash
            FROM actions a
            JOIN action_metadata am ON a.id = am.action_id
            WHERE am.source_file = ?
            LIMIT 1
        """, (str(file_path),))

        result = cursor.fetchone()

        if not result:
            # Not indexed yet
            return (True, None)

        action_id, stored_hash = result

        if stored_hash == current_hash:
            # File unchanged
            return (False, action_id)
        else:
            # File changed
            return (True, action_id)

    def _save_with_file_metadata(
        self,
        content: str,
        file_path: Path,
        file_hash: str,
        action_type: str,
        project: str,
        existing_action_id: Optional[int] = None
    ) -> int:
        """
        Save or update action with file tracking metadata.

        Args:
            content: Content to save
            file_path: Source file path
            file_hash: File content hash
            action_type: Action type
            project: Project name
            existing_action_id: If provided, updates existing action instead of creating new

        Returns:
            Action ID
        """
        import time

        if existing_action_id:
            # Update existing entry
            cursor = self.conn.cursor()

            # Update action timestamp
            cursor.execute("""
                UPDATE actions
                SET timestamp = ?
                WHERE id = ?
            """, (int(time.time()), existing_action_id))

            # Update content via UPSERT
            content_hash = hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()
            cursor.execute("""
                INSERT INTO action_content (action_id, content, content_hash)
                VALUES (?, ?, ?)
                ON CONFLICT (action_id) DO UPDATE SET
                    content = EXCLUDED.content,
                    content_hash = EXCLUDED.content_hash
            """, (existing_action_id, content, content_hash))

            # Update metadata via UPSERT
            indexed_at = int(time.time())
            cursor.execute("""
                INSERT INTO action_metadata (action_id, source_file, source_hash, indexed_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (action_id) DO UPDATE SET
                    source_file = EXCLUDED.source_file,
                    source_hash = EXCLUDED.source_hash,
                    indexed_at = EXCLUDED.indexed_at
            """, (existing_action_id, str(file_path), file_hash, indexed_at))

            self.conn.commit()
            return existing_action_id
        else:
            # Create new entry via save_callback
            action_id = self.save_callback(content, action_type=action_type, project=project)

            if action_id > 0:
                # Add file tracking metadata via UPSERT
                cursor = self.conn.cursor()
                indexed_at = int(time.time())
                cursor.execute("""
                    INSERT INTO action_metadata (action_id, source_file, source_hash, indexed_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (action_id) DO UPDATE SET
                        source_file = EXCLUDED.source_file,
                        source_hash = EXCLUDED.source_hash,
                        indexed_at = EXCLUDED.indexed_at
                """, (action_id, str(file_path), file_hash, indexed_at))
                self.conn.commit()

            return action_id

    def index_md_files(
        self,
        directory: str = '.',
        custom_keywords: List[str] = None
    ) -> int:
        """
        Index all MD files in directory recursively.

        Args:
            directory: Directory to index
            custom_keywords: Additional keywords to consider important

        Returns:
            Number of files indexed

        Process:
        1. Find all *.md files recursively
        2. Extract important sections based on keywords
        3. Save full file content
        4. Save important sections separately
        5. Extract special patterns (commands, scripts, paths)
        """
        indexed = 0
        project = Path.cwd().name
        project_id = self.db.get_or_create_project(project)

        important_sections = self._build_keyword_set(project, custom_keywords)

        base_path = Path(directory)
        for md_file in base_path.rglob('*.md'):
            try:
                if any(part in self.SKIP_DIRECTORIES for part in md_file.parts):
                    continue

                # Read content
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                file_hash = hashlib.md5(content.encode('utf-8'), usedforsecurity=False).hexdigest()

                # Check if re-index needed
                needs_reindex, existing_id = self._check_if_needs_reindex(md_file.absolute(), file_hash)

                if not needs_reindex:
                    print(f"  ⏭️  Skipped (unchanged): {md_file.name}")
                    continue

                # Save or update with file tracking
                summary = ' '.join(content.split()[:100])
                action_id = self._save_with_file_metadata(
                    content=f"MD File: {md_file}\n{summary}",
                    file_path=md_file.absolute(),
                    file_hash=file_hash,
                    action_type='docs',
                    project=project,
                    existing_action_id=existing_id
                )

                if action_id > 0:
                    if existing_id:
                        print(f"  🔄 Updated: {md_file.name}")
                    else:
                        print(f"  ✅ Indexed: {md_file.name}")
                    indexed += 1

                    self._extract_sections(content, md_file, project, important_sections, file_hash)
                    self._extract_special_patterns(content, md_file, project, file_hash)

            except Exception as e:
                print(f"Error indexing {md_file}: {e}")

        print(f"✅ {indexed} MD-Dateien indexiert")
        return indexed

    def _build_keyword_set(
        self,
        project: str,
        custom_keywords: List[str] = None
    ) -> Set[str]:
        """
        Build complete keyword set from defaults + config + custom.

        Args:
            project: Project name
            custom_keywords: Additional keywords

        Returns:
            Set of lowercase keywords
        """
        keywords = set(self.DEFAULT_KEYWORDS)

        if self.custom_keywords and 'project_keywords' in self.custom_keywords:
            proj_keywords = self.custom_keywords['project_keywords']
            if project in proj_keywords:
                keywords.update(proj_keywords[project])
            if 'default' in proj_keywords:
                keywords.update(proj_keywords['default'])

        if custom_keywords:
            keywords.update(custom_keywords)

        return {k.lower() for k in keywords}

    def _extract_sections(
        self,
        content: str,
        file_path: Path,
        project: str,
        important_sections: Set[str],
        file_hash: str = None
    ) -> None:
        """
        Extract and save important MD sections.

        Args:
            content: File content
            file_path: Path to file
            project: Project name
            important_sections: Set of important keywords

        Sections starting with ## or ### are checked against keywords.
        """
        lines = content.split('\n')
        current_section = None
        section_content = []

        for line in lines:
            if line.startswith('##'):
                if current_section and section_content:
                    self._save_section_if_important(
                        current_section,
                        section_content,
                        file_path,
                        project,
                        important_sections
                    )

                current_section = line.strip('#').strip()
                section_content = []
            elif current_section:
                section_content.append(line)

        if current_section and section_content:
            self._save_section_if_important(
                current_section,
                section_content,
                file_path,
                project,
                important_sections
            )

    def _save_section_if_important(
        self,
        section_title: str,
        section_lines: List[str],
        file_path: Path,
        project: str,
        important_sections: Set[str]
    ) -> None:
        """
        Save section if it matches important keywords.

        Args:
            section_title: Section title
            section_lines: Lines in section
            file_path: Path to file
            project: Project name
            important_sections: Important keyword set
        """
        if not any(keyword in section_title.lower() for keyword in important_sections):
            return

        section_text = '\n'.join(section_lines)
        self.save_callback(
            f"📌 WICHTIG aus {file_path.name}:\n"
            f"Section: {section_title}\n"
            f"{section_text[:1000]}",
            action_type='instruction',
            project=project
        )

    def _extract_special_patterns(
        self,
        content: str,
        file_path: Path,
        project: str,
        file_hash: str = None
    ) -> None:
        """
        Extract special patterns from MD content.

        Extracts:
        - SSH/SCP commands
        - Docker commands
        - Script paths
        - Important file paths

        Args:
            content: File content
            file_path: Path to file
            project: Project name
        """
        ssh_commands = re.findall(r'(ssh\s+[\w\-]+.*?)(?:\n|$)', content)
        for cmd in ssh_commands[:5]:
            if len(cmd) > 20:
                self.save_callback(
                    f"🔧 SSH Command aus {file_path.name}:\n{cmd}",
                    action_type='command',
                    project=project
                )

        docker_commands = re.findall(r'(docker(?:\s+compose)?\s+.*?)(?:\n|$)', content)
        for cmd in docker_commands[:5]:
            if len(cmd) > 20:
                self.save_callback(
                    f"🐳 Docker Command aus {file_path.name}:\n{cmd}",
                    action_type='command',
                    project=project
                )

        script_paths = re.findall(r'([./][\w/]+\.(?:sh|py|js|rb|pl))', content)
        for script in set(script_paths[:10]):
            self.save_callback(
                f"📜 Script-Referenz aus {file_path.name}: {script}",
                action_type='reference',
                project=project
            )

        important_paths = re.findall(r'(/(?:home|apps|var|etc|usr)/[\w\-/\.]+)', content)
        for path in set(important_paths[:10]):
            if len(path) > 10 and not path.endswith('/'):
                self.save_callback(
                    f"📁 Wichtiger Pfad aus {file_path.name}: {path}",
                    action_type='path',
                    project=project
                )
