#!/usr/bin/env python3
"""
Test Git Integration
"""

import unittest
import tempfile
import shutil
import subprocess
from pathlib import Path
import sys
import os

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.features.git_integration import GitIntegration


class TestGitIntegration(unittest.TestCase):
    """Test Git Integration functionality"""

    def setUp(self):
        """Create temporary git repo for testing"""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Initialize git repo
        subprocess.run(['git', 'init'], capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@test.com'], capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test User'], capture_output=True)

        # Create test file and initial commit
        Path('test.txt').write_text('initial content')
        subprocess.run(['git', 'add', 'test.txt'], capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'Initial commit'], capture_output=True)

        self.git = GitIntegration()

    def tearDown(self):
        """Clean up test directory"""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_is_git_repo(self):
        """Test git repository detection"""
        self.assertTrue(self.git.is_git_repo())

        # Test non-git directory
        non_git_dir = tempfile.mkdtemp()
        try:
            self.assertFalse(self.git.is_git_repo(Path(non_git_dir)))
        finally:
            shutil.rmtree(non_git_dir)

    def test_get_git_info(self):
        """Test getting git repository information"""
        info = self.git.get_git_info()

        self.assertIsNotNone(info)
        self.assertIn('branch', info)
        self.assertIn('last_commit', info)
        self.assertIn('repo_name', info)
        self.assertIn('has_changes', info)

        # Initially no changes
        self.assertFalse(info['has_changes'])

        # Make changes
        Path('test.txt').write_text('modified content')
        info = self.git.get_git_info()
        self.assertTrue(info['has_changes'])

    def test_hook_installation(self):
        """Test hook installation"""
        # Initially no hook
        self.assertFalse(self.git.has_cm_hook())

        # Install hook
        result = self.git.install_hook()
        self.assertTrue(result)

        # Verify hook exists
        self.assertTrue(self.git.has_cm_hook())
        hook_path = Path('.git/hooks/post-commit')
        self.assertTrue(hook_path.exists())
        self.assertTrue(hook_path.stat().st_mode & 0o111)  # Check executable

        # Verify hook content
        content = hook_path.read_text()
        self.assertIn(GitIntegration.HOOK_MARKER, content)
        self.assertIn('context_manager.py', content)
        self.assertIn(f"# Hook Version: {GitIntegration.HOOK_VERSION}", content)

    def test_hook_already_installed(self):
        """Test behavior when hook is already installed"""
        # Install once
        self.git.install_hook()
        self.assertTrue(self.git.has_cm_hook())

        # Try to install again (should succeed without overwriting)
        result = self.git.install_hook()
        self.assertTrue(result)

        # Verify still installed
        self.assertTrue(self.git.has_cm_hook())

    def test_generate_hook_content(self):
        """Test hook content generation"""
        content = self.git.generate_hook_content()

        # Check essential parts
        self.assertIn('#!/bin/bash', content)
        self.assertIn(GitIntegration.HOOK_MARKER, content)
        self.assertIn(f"# Hook Version: {GitIntegration.HOOK_VERSION}", content)
        self.assertIn('python3 <<\'PY\'', content)
        self.assertIn('export CM_CONTEXT_MANAGER_PATH', content)
        self.assertIn('export CM_MESSAGE', content)
        self.assertIn('with open(os.devnull, "wb") as devnull', content)

    def test_different_branch(self):
        """Test git info on different branch"""
        # Create and switch to new branch
        subprocess.run(['git', 'checkout', '-b', 'test-branch'], capture_output=True)

        info = self.git.get_git_info()
        self.assertEqual(info['branch'], 'test-branch')


if __name__ == '__main__':
    unittest.main(verbosity=2)
