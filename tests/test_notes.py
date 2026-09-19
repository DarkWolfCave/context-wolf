#!/usr/bin/env python3
"""
Tests for NotesManager surgical-edit and partial-read helpers:
replace_in_note, grep_note, get_note_slice.

Like test_now.py these run against the live PostgreSQL connection (the
string/line logic is the hard part and mocking the DB would defeat the
purpose). Each test cleans up the notes it creates. The suite skips itself
when no database connection is available.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.features.notes import NotesManager


def _db_available() -> bool:
    try:
        from src.core.database import Database
        db = Database()
        db.close()
        return True
    except Exception:
        return False


@unittest.skipUnless(_db_available(), "No PostgreSQL connection available")
class TestNotesEditAndRead(unittest.TestCase):
    """End-to-end tests for the surgical-edit / partial-read helpers."""

    @classmethod
    def setUpClass(cls):
        from src.core.database import Database
        cls.db = Database()
        cls.nm = NotesManager(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self._created = []

    def tearDown(self):
        for nid in self._created:
            try:
                self.nm.delete_note(nid)
            except Exception:
                pass

    def _make(self, content, title="test-notes-helper"):
        nid = self.nm.add_note(title=title, content=content, tags="test-notes-helper")
        self._created.append(nid)
        return nid

    # ---- replace_in_note -------------------------------------------------

    def test_replace_single_occurrence(self):
        nid = self._make("alpha beta gamma")
        res = self.nm.replace_in_note(nid, "beta", "BETA")
        self.assertEqual(res["replaced"], 1)
        self.assertEqual(self.nm.get_note(nid)["content"], "alpha BETA gamma")

    def test_replace_not_found_raises(self):
        nid = self._make("alpha beta gamma")
        with self.assertRaises(ValueError):
            self.nm.replace_in_note(nid, "delta", "x")

    def test_replace_ambiguous_raises_without_replace_all(self):
        nid = self._make("dup dup dup")
        with self.assertRaises(ValueError):
            self.nm.replace_in_note(nid, "dup", "x")
        # content untouched after the failed edit
        self.assertEqual(self.nm.get_note(nid)["content"], "dup dup dup")

    def test_replace_all_replaces_every_occurrence(self):
        nid = self._make("dup dup dup")
        res = self.nm.replace_in_note(nid, "dup", "x", replace_all=True)
        self.assertEqual(res["replaced"], 3)
        self.assertEqual(self.nm.get_note(nid)["content"], "x x x")

    def test_replace_empty_new_string_deletes_span(self):
        nid = self._make("keep DROP keep")
        self.nm.replace_in_note(nid, " DROP", "")
        self.assertEqual(self.nm.get_note(nid)["content"], "keep keep")

    def test_replace_empty_old_string_raises(self):
        nid = self._make("content")
        with self.assertRaises(ValueError):
            self.nm.replace_in_note(nid, "", "x")

    def test_replace_identical_strings_raises(self):
        nid = self._make("content")
        with self.assertRaises(ValueError):
            self.nm.replace_in_note(nid, "content", "content")

    def test_replace_unknown_note_raises(self):
        with self.assertRaises(ValueError):
            self.nm.replace_in_note(999_999_999, "a", "b")

    def test_replace_over_length_refused(self):
        nid = self._make("X" + "y" * 100)
        # Blow past MAX_CONTENT_LENGTH via a huge replacement.
        big = "z" * (NotesManager.MAX_CONTENT_LENGTH + 10)
        with self.assertRaises(ValueError):
            self.nm.replace_in_note(nid, "X", big)
        # original content preserved
        self.assertTrue(self.nm.get_note(nid)["content"].startswith("X"))

    def test_replace_preserves_whitespace_and_newlines(self):
        nid = self._make("line1\n  indented old\nline3")
        self.nm.replace_in_note(nid, "  indented old", "  indented new")
        self.assertEqual(
            self.nm.get_note(nid)["content"], "line1\n  indented new\nline3"
        )

    # ---- grep_note -------------------------------------------------------

    def test_grep_finds_line_with_context(self):
        nid = self._make("a\nb\nTARGET\nd\ne")
        res = self.nm.grep_note(nid, "TARGET", context=1)
        self.assertEqual(res["match_count"], 1)
        self.assertEqual(res["total_lines"], 5)
        block = res["blocks"][0]["lines"]
        # context=1 -> lines 2,3,4 (1-based)
        self.assertEqual([l["n"] for l in block], [2, 3, 4])
        match_line = [l for l in block if l["is_match"]][0]
        self.assertEqual(match_line["n"], 3)
        self.assertEqual(match_line["text"], "TARGET")

    def test_grep_no_match(self):
        nid = self._make("a\nb\nc")
        res = self.nm.grep_note(nid, "zzz")
        self.assertEqual(res["match_count"], 0)
        self.assertEqual(res["blocks"], [])

    def test_grep_merges_overlapping_context(self):
        nid = self._make("m\nx\nm\ny\nz")
        res = self.nm.grep_note(nid, "^m$", context=1)
        # matches on lines 1 and 3; context windows overlap -> single block
        self.assertEqual(res["match_count"], 2)
        self.assertEqual(len(res["blocks"]), 1)

    def test_grep_case_insensitive_default(self):
        nid = self._make("Hello World")
        res = self.nm.grep_note(nid, "hello")
        self.assertEqual(res["match_count"], 1)

    def test_grep_invalid_regex_raises(self):
        nid = self._make("content")
        with self.assertRaises(ValueError):
            self.nm.grep_note(nid, "(unclosed")

    def test_grep_gives_editable_old_string(self):
        # The core promise: grep locates text, that text edits cleanly.
        nid = self._make("intro\nsome OLD value here\noutro")
        res = self.nm.grep_note(nid, "OLD", context=0)
        text = res["blocks"][0]["lines"][0]["text"]
        self.nm.replace_in_note(nid, text, "some NEW value here")
        self.assertIn("some NEW value here", self.nm.get_note(nid)["content"])

    # ---- get_note_slice --------------------------------------------------

    def test_slice_returns_range_inclusive(self):
        nid = self._make("l1\nl2\nl3\nl4\nl5")
        res = self.nm.get_note_slice(nid, start_line=2, end_line=4)
        self.assertEqual(res["content"], "l2\nl3\nl4")
        self.assertEqual(res["slice_start"], 2)
        self.assertEqual(res["slice_end"], 4)
        self.assertEqual(res["total_lines"], 5)

    def test_slice_defaults_to_full(self):
        nid = self._make("l1\nl2\nl3")
        res = self.nm.get_note_slice(nid)
        self.assertEqual(res["content"], "l1\nl2\nl3")

    def test_slice_clamps_end_beyond_total(self):
        nid = self._make("l1\nl2")
        res = self.nm.get_note_slice(nid, start_line=2, end_line=999)
        self.assertEqual(res["content"], "l2")

    def test_slice_invalid_range_raises(self):
        nid = self._make("l1\nl2\nl3")
        with self.assertRaises(ValueError):
            self.nm.get_note_slice(nid, start_line=3, end_line=1)

    def test_slice_unknown_note_returns_none(self):
        self.assertIsNone(self.nm.get_note_slice(999_999_999))


if __name__ == "__main__":
    unittest.main()
