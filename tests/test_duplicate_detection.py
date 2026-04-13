#!/usr/bin/env python3
"""
Test Duplicate Detection Functionality
"""

import unittest
import tempfile
import sqlite3
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.duplicate_detector import DuplicateDetector


class TestDuplicateDetection(unittest.TestCase):
    """Test Duplicate Detection functionality"""

    def setUp(self):
        """Create test database"""
        # Create temporary database
        self.test_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.conn = sqlite3.connect(self.test_db.name)
        self.conn.row_factory = sqlite3.Row

        # Create minimal schema for testing
        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE action_types (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE actions (
                id INTEGER PRIMARY KEY,
                timestamp INTEGER DEFAULT (unixepoch()),
                type_id INTEGER,
                project_id INTEGER,
                summary TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE action_content (
                action_id INTEGER PRIMARY KEY,
                content TEXT,
                content_hash TEXT
            )
        """)

        # Insert test data
        cursor.execute("INSERT INTO projects (name) VALUES ('test-project')")
        cursor.execute("INSERT INTO action_types (name) VALUES ('feature')")

        # Add some test entries
        test_entries = [
            (1, "Login Bug fixed with authentication", "Fixed the login bug in the authentication module"),
            (2, "Database connection optimized", "Optimized database connection pool for better performance"),
            (3, "Login authentication bug resolved", "Resolved the authentication bug in login system"),
            (4, "API endpoint created", "Created new REST API endpoint for user management"),
            (5, "Database pool connection improved", "Improved the connection pool for database")
        ]

        for entry_id, summary, content in test_entries:
            cursor.execute("""
                INSERT INTO actions (id, type_id, project_id, summary, timestamp)
                VALUES (?, 1, 1, ?, unixepoch() - ?)
            """, (entry_id, summary, entry_id * 3600))  # Different timestamps

            cursor.execute("""
                INSERT INTO action_content (action_id, content, content_hash)
                VALUES (?, ?, ?)
            """, (entry_id, content, f"hash_{entry_id}"))

        self.conn.commit()

        # Initialize DuplicateDetector
        self.detector = DuplicateDetector(self.conn)
        self.detector.create_relations_table()

    def tearDown(self):
        """Clean up test database"""
        self.conn.close()
        Path(self.test_db.name).unlink()

    def test_similarity_calculation(self):
        """Test text similarity calculation"""
        text1 = "Login Bug fixed"
        text2 = "Login Bug resolved"
        text3 = "Database optimized"

        sim1_2 = self.detector.calculate_similarity(text1, text2)
        sim1_3 = self.detector.calculate_similarity(text1, text3)

        # Similar texts should have high similarity
        self.assertGreater(sim1_2, 0.7)
        # Different texts should have low similarity
        self.assertLess(sim1_3, 0.4)  # Adjusted threshold

    def test_find_similar_entries(self):
        """Test finding similar entries"""
        # Test with login-related content
        similar = self.detector.find_similar_entries(
            "Login authentication bug has been fixed",
            project="test-project"
        )

        # Should find the similar login entries
        self.assertGreater(len(similar), 0)

        # Most similar should be login-related
        top_match = similar[0] if similar else None
        if top_match:
            self.assertIn("login", top_match['content'].lower())
            self.assertGreater(top_match['similarity'], 0.5)

    def test_categorization(self):
        """Test similarity categorization"""
        # Test exact duplicate
        category = self.detector._categorize_similarity(0.95, True, 0.5)
        self.assertEqual(category, "exact_duplicate")

        # Test likely duplicate
        category = self.detector._categorize_similarity(0.85, True, 20)
        self.assertEqual(category, "likely_duplicate")

        # Test related content
        category = self.detector._categorize_similarity(0.70, True, 100)
        self.assertEqual(category, "related_content")

        # Test cross reference
        category = self.detector._categorize_similarity(0.75, False, 50)
        self.assertEqual(category, "cross_reference")

    def test_check_for_duplicates(self):
        """Test duplicate checking"""
        # Check for exact duplicate
        result = self.detector.check_for_duplicates(
            "Login authentication bug resolved",
            project="test-project"
        )

        # Should find similar entry
        self.assertTrue(len(result['similar_entries']) > 0)

        # Check with completely different content
        result = self.detector.check_for_duplicates(
            "Implementing new feature for payment processing",
            project="test-project"
        )

        # Should not warn for unrelated content
        self.assertFalse(result['should_warn'])

    def test_save_and_retrieve_relations(self):
        """Test saving and retrieving relations"""
        # Save a relation
        self.detector.save_relation(1, 3, 0.85, "likely_duplicate")

        # Retrieve relations
        related = self.detector.get_related_entries(1)

        # Should find the related entry
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0]['similarity_score'], 0.85)
        self.assertEqual(related[0]['relation_type'], "likely_duplicate")

    def test_time_ago_formatting(self):
        """Test time difference formatting"""
        from datetime import timedelta

        # Test various time differences
        self.assertEqual(self.detector._format_time_ago(timedelta(seconds=30)), "gerade eben")
        self.assertEqual(self.detector._format_time_ago(timedelta(minutes=5)), "vor 5 Minuten")
        self.assertEqual(self.detector._format_time_ago(timedelta(hours=2)), "vor 2 Stunden")
        self.assertEqual(self.detector._format_time_ago(timedelta(days=3)), "vor 3 Tagen")

    def test_cache_performance(self):
        """Test similarity cache for performance"""
        text1 = "Test content for caching"
        text2 = "Another test content"

        # First calculation
        sim1 = self.detector.calculate_similarity(text1, text2)

        # Second calculation (should use cache)
        sim2 = self.detector.calculate_similarity(text1, text2)

        # Results should be identical
        self.assertEqual(sim1, sim2)

        # Cache should contain the result
        self.assertGreater(len(self.detector.similarity_cache), 0)

    def test_empty_database(self):
        """Test behavior with empty database"""
        # Clear all entries
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM actions")
        cursor.execute("DELETE FROM action_content")
        self.conn.commit()

        # Should handle empty database gracefully
        similar = self.detector.find_similar_entries("Test content", "test-project")
        self.assertEqual(len(similar), 0)

        result = self.detector.check_for_duplicates("Test content", "test-project")
        self.assertFalse(result['has_duplicates'])
        self.assertFalse(result['should_warn'])


if __name__ == '__main__':
    unittest.main(verbosity=2)