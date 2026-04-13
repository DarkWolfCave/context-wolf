#!/usr/bin/env python3
"""
Test Token Tracking Estimation Logic
"""

import unittest
import sys
from pathlib import Path

# Add project root to path to allow importing from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.features.token_tracking import TokenTracker

class TestTokenEstimation(unittest.TestCase):
    """Test the token estimation logic is calculated as expected."""

    def setUp(self):
        """Initialize the TokenTracker for testing."""
        self.tracker = TokenTracker(stats_file=None)
        print("\n" + '-'*70)

    def tearDown(self):
        print('-'*70)

    def _run_test_case(self, name, text, expected_tokens):
        """Helper function to run and print a single test case."""
        print(f"🧪 Testfall: {name}")
        print(f"   Input: '{text[:50]}...'")
        
        actual_tokens = self.tracker.estimate_tokens(text)
        
        print(f"   -> SOLL (erwartet): {expected_tokens}")
        print(f"   -> IST  (berechnet): {actual_tokens}")
        
        self.assertEqual(actual_tokens, expected_tokens)
        print("   => ✅ PASSED")

    def test_estimate_tokens_verbose(self):
        """Verify the token estimation formula with verbose output."""
        test_cases = [
            ("Leerer Text", "", 0),
            ("Einfacher Text", "Hello world", 2),
            ("Kurzer deutscher Satz", "Nutze PostgreSQL als Haupt-Datenbank", 9),
            ("Mittellanger englischer Satz", "scope todo list to current project by default", 11),
            ("Viele kurze Wörter", "a b c d e f g", 9),
            ("Text mit Sonderzeichen", """Test!@#$%^&*()=+[]{};:'",./<>?`~""", 8)
        ]
        
        for name, text, expected in test_cases:
            with self.subTest(name=name):
                self._run_test_case(name, text, expected)


if __name__ == '__main__':
    unittest.main(verbosity=2)