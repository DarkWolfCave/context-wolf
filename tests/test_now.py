#!/usr/bin/env python3
"""
Tests for the "Now" sprint-backlog manager.

These tests use a real PostgreSQL connection (the same one the CLI uses)
because the NowManager is small and the JOIN-based link resolver is the
hard part to get right - mocking it would defeat the purpose. The tests
work against the configured database but isolate themselves by deleting
any rows they create at the end.

Skipped automatically when no DB connection is available so the suite
stays runnable on machines without PostgreSQL.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.features.now import (
    NowManager,
    NowLimitExceeded,
    BUCKETS,
    ACTIVE_BUCKETS,
    DEFAULT_LIMITS,
    LINKED_TYPES,
)


def _db_available() -> bool:
    try:
        from src.core.database import Database
        db = Database()
        db.close()
        return True
    except Exception:
        return False


@unittest.skipUnless(_db_available(), "No PostgreSQL connection available")
class TestNowManager(unittest.TestCase):
    """End-to-end tests for NowManager against the live DB."""

    @classmethod
    def setUpClass(cls):
        from src.core.database import Database
        cls.db = Database()
        cls.nm = NowManager(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        # Per-test scratch list - cleared in tearDown so tests don't pile
        # rows up on the live DB or starve later WIP-limit tests.
        self._created_ids = []

    def tearDown(self):
        if self._created_ids:
            cursor = self.db.conn.cursor()
            placeholders = ",".join(["?"] * len(self._created_ids))
            cursor.execute(
                f"DELETE FROM now_items WHERE id IN ({placeholders})",
                self._created_ids,
            )
            self.db.conn.commit()
        self._created_ids = []

    def _add(self, **kwargs):
        item_id = self.nm.add_item(**kwargs)
        self._created_ids.append(item_id)
        return item_id

    # ------------------ static constants ------------------

    def test_constants_match_migration(self):
        self.assertEqual(BUCKETS, ("today", "week", "later", "done"))
        self.assertEqual(ACTIVE_BUCKETS, ("today", "week", "later"))
        self.assertEqual(DEFAULT_LIMITS, {"today": 7, "week": 20, "later": 50})
        self.assertIn("todo", LINKED_TYPES)
        self.assertIn("service", LINKED_TYPES)

    # ------------------ add / list ------------------

    def test_add_freeform_and_list(self):
        item_id = self._add(title="Unit test free-form item", bucket="today")
        self.assertIsInstance(item_id, int)

        data = self.nm.list_items()
        ids = [i["id"] for i in data["items"]]
        self.assertIn(item_id, ids)

        item = next(i for i in data["items"] if i["id"] == item_id)
        self.assertEqual(item["bucket"], "today")
        self.assertEqual(item["title"], "Unit test free-form item")
        self.assertIsNone(item["linked"])
        # Response contract: counts and limits are always present.
        self.assertIn("counts", data)
        self.assertIn("limits", data)
        for b in BUCKETS:
            self.assertIn(b, data["counts"])
        for b in ACTIVE_BUCKETS:
            self.assertIn(b, data["limits"])

    def test_add_with_invalid_bucket_rejected(self):
        with self.assertRaises(ValueError):
            self.nm.add_item(title="bad", bucket="someday")

    def test_add_with_invalid_linked_type_rejected(self):
        with self.assertRaises(ValueError):
            self.nm.add_item(title="bad", linked_type="banana", linked_id=1)

    def test_add_link_requires_both_fields(self):
        with self.assertRaises(ValueError):
            self.nm.add_item(title="bad", linked_type="note")

    def test_add_into_done_rejected(self):
        with self.assertRaises(ValueError):
            self.nm.add_item(title="x", bucket="done")

    def test_add_empty_title_rejected(self):
        with self.assertRaises(ValueError):
            self.nm.add_item(title="   ", bucket="today")

    def test_add_overlong_title_rejected_not_truncated(self):
        # An over-long title must be rejected loudly, never silently chopped
        # to MAX_TITLE_LENGTH - Now items have no body, so a truncated title
        # would lose everything past the cutoff for good.
        too_long = "A" * (self.nm.MAX_TITLE_LENGTH + 50)
        with self.assertRaises(ValueError):
            self.nm.add_item(title=too_long, bucket="today")
        # And nothing was persisted as a side effect of the rejection.
        self.assertEqual(self.nm._count_bucket("today"), 0)

    def test_add_title_at_limit_accepted(self):
        exact = "B" * self.nm.MAX_TITLE_LENGTH
        item_id = self._add(title=exact, bucket="today")
        item = self.nm.get_item(item_id)
        self.assertEqual(item["title"], exact)
        self.assertEqual(len(item["title"]), self.nm.MAX_TITLE_LENGTH)

    # ------------------ move ------------------

    def test_move_between_active_buckets(self):
        item_id = self._add(title="Move me", bucket="today")
        result = self.nm.move_item(item_id, "later")
        self.assertTrue(result["moved"])
        self.assertEqual(result["from"], "today")
        self.assertEqual(result["bucket"], "later")

        # Idempotent: moving to the same bucket is a no-op.
        result2 = self.nm.move_item(item_id, "later")
        self.assertFalse(result2["moved"])

    def test_move_to_done_via_helper(self):
        # Direct move() into 'done' is forbidden - must go through mark_done().
        item_id = self._add(title="Finish me", bucket="today")
        with self.assertRaises(ValueError):
            self.nm.move_item(item_id, "done")

        self.nm.mark_done(item_id)
        item = self.nm.get_item(item_id)
        self.assertEqual(item["bucket"], "done")
        self.assertIsNotNone(item["done_at"])

    # ------------------ edit ------------------

    def test_edit_title_renames_in_place(self):
        item_id = self._add(title="Old title", bucket="today")
        result = self.nm.edit_title(item_id, "New title")
        self.assertEqual(result["title"], "New title")
        item = self.nm.get_item(item_id)
        self.assertEqual(item["title"], "New title")
        # In place: same id, same bucket - no delete+re-add side effects.
        self.assertEqual(item["id"], item_id)
        self.assertEqual(item["bucket"], "today")

    def test_edit_title_unknown_item_rejected(self):
        with self.assertRaises(ValueError):
            self.nm.edit_title(999999, "whatever")

    def test_edit_title_empty_rejected(self):
        item_id = self._add(title="Keep me", bucket="today")
        with self.assertRaises(ValueError):
            self.nm.edit_title(item_id, "   ")
        # Original title untouched after a rejected edit.
        self.assertEqual(self.nm.get_item(item_id)["title"], "Keep me")

    def test_edit_title_overlong_rejected_not_truncated(self):
        item_id = self._add(title="Short", bucket="today")
        too_long = "Z" * (self.nm.MAX_TITLE_LENGTH + 10)
        with self.assertRaises(ValueError):
            self.nm.edit_title(item_id, too_long)
        # Same validation as add_item - no silent truncation on edit either.
        self.assertEqual(self.nm.get_item(item_id)["title"], "Short")

    # ------------------ limits ------------------

    def _bucket_count(self, bucket: str) -> int:
        cursor = self.db.conn.cursor()
        row = cursor.execute(
            "SELECT COUNT(*) AS c FROM now_items WHERE bucket = ?", (bucket,)
        ).fetchone()
        return int(row["c"])

    def test_wip_limit_blocks_add(self):
        # Set the 'today' limit to "two more than what's currently in the
        # bucket" so we know exactly when the next add should fail.
        original = self.nm.get_settings()
        existing = self._bucket_count("today")
        target_limit = existing + 2
        if target_limit > 100:
            self.skipTest("'today' bucket already near the hard cap")
        created = []
        try:
            self.nm.update_settings(today=target_limit)
            created.append(self._add(title="cap1", bucket="today"))
            created.append(self._add(title="cap2", bucket="today"))
            with self.assertRaises(NowLimitExceeded) as ctx:
                self.nm.add_item(title="cap3-overflow", bucket="today")
            self.assertEqual(ctx.exception.bucket, "today")
            self.assertEqual(ctx.exception.limit, target_limit)
            self.assertEqual(ctx.exception.current, target_limit)
        finally:
            for cid in created:
                try:
                    self.nm.remove_item(cid)
                except Exception:
                    pass
            self._created_ids = [i for i in self._created_ids if i not in created]
            self.nm.update_settings(today=original["today"])

    def test_wip_limit_blocks_move(self):
        original = self.nm.get_settings()
        existing_week = self._bucket_count("week")
        # Pin 'week' to exactly its current size so the very next move into
        # it overflows.
        target_limit = max(existing_week, 1)
        created = []
        try:
            self.nm.update_settings(week=target_limit)
            in_today = self._add(title="src", bucket="today")
            created.append(in_today)
            if existing_week == 0:
                # We need at least one item in 'week' to hit the cap.
                filler = self._add(title="filler", bucket="week")
                created.append(filler)
            with self.assertRaises(NowLimitExceeded):
                self.nm.move_item(in_today, "week")
        finally:
            for cid in created:
                try:
                    self.nm.remove_item(cid)
                except Exception:
                    pass
            self._created_ids = [i for i in self._created_ids if i not in created]
            self.nm.update_settings(week=original["week"])

    # ------------------ done lifecycle ------------------

    def test_mark_done_then_show(self):
        item_id = self._add(title="Done lifecycle", bucket="week")
        self.nm.mark_done(item_id)
        item = self.nm.get_item(item_id)
        self.assertEqual(item["bucket"], "done")
        self.assertIsNotNone(item["done_at"])

        # Default list omits done items.
        data = self.nm.list_items()
        self.assertNotIn(item_id, [i["id"] for i in data["items"]])

        # include_done flips it.
        data_all = self.nm.list_items(include_done=True)
        self.assertIn(item_id, [i["id"] for i in data_all["items"]])

    # ------------------ linked entity resolution ------------------

    def test_linked_payload_for_dangling_id(self):
        # ID large enough that no note can plausibly exist for it.
        item_id = self._add(
            title="dangling link",
            linked_type="note",
            linked_id=999_999_999,
        )
        item = self.nm.get_item(item_id)
        self.assertIsNotNone(item["linked"])
        self.assertEqual(item["linked"]["type"], "note")
        self.assertEqual(item["linked"]["id"], 999_999_999)
        self.assertFalse(item["linked"]["exists"])

    # ------------------ settings ------------------

    def test_settings_round_trip(self):
        original = self.nm.get_settings()
        try:
            new = self.nm.update_settings(today=5, week=15, later=40)
            self.assertEqual(new, {"today": 5, "week": 15, "later": 40})
        finally:
            self.nm.update_settings(
                today=original["today"],
                week=original["week"],
                later=original["later"],
            )

    def test_settings_clamp(self):
        with self.assertRaises(ValueError):
            self.nm.update_settings(today=0)
        with self.assertRaises(ValueError):
            self.nm.update_settings(today=101)

    # ------------------ reorder ------------------

    def test_reorder_requires_exact_match(self):
        a = self._add(title="r-a", bucket="later")
        b = self._add(title="r-b", bucket="later")
        c = self._add(title="r-c", bucket="later")

        # Bucket may have other rows from earlier tests in 'later' too,
        # so use exactly what's there at this point.
        cursor = self.db.conn.cursor()
        rows = cursor.execute(
            "SELECT id FROM now_items WHERE bucket = 'later' ORDER BY position"
        ).fetchall()
        in_bucket = [r["id"] for r in rows]

        # Pass the exact same set in reversed order.
        reversed_ids = list(reversed(in_bucket))
        self.nm.reorder_bucket("later", reversed_ids)

        rows_after = cursor.execute(
            "SELECT id FROM now_items WHERE bucket = 'later' ORDER BY position"
        ).fetchall()
        self.assertEqual([r["id"] for r in rows_after], reversed_ids)

        # Reorder with mismatched set rejects.
        with self.assertRaises(ValueError):
            self.nm.reorder_bucket("later", reversed_ids + [999_999])


if __name__ == "__main__":
    unittest.main()
