"""Regression: operator-reviewed canonical edits are fenced and fail closed."""
from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from skeleton.jeeves.worlds.laptop_flow import LaptopFlow
from skeleton.jeeves.worlds.world_canon import CanonError


BRIEF = {
    "id": "review-atomic", "premise": "A traveler crosses the marsh.",
    "protagonist": "Mira", "region": "North Marsh",
    "goal": "Return with a map",
}
OPERATION = {
    "action": "replace_scene",
    "value": {
        "id": "opening", "title": "Mira surveys the marsh",
        "narrative": "The traveler records the safe path.",
    },
}
NOTE = "Reviewed the authored opening and verified its continuity."


class AtomicReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.flow = LaptopFlow(self.temp.name)
        self.initial = self.flow.propose(BRIEF)["source_digest"]

    def test_preview_is_deterministic_and_does_not_publish_or_approve(self):
        first = self.flow.preview_edit(BRIEF["id"], self.initial, OPERATION)
        second = self.flow.preview_edit(BRIEF["id"], self.initial, OPERATION)
        self.assertEqual(first, second)
        self.assertEqual(first["changes"]["scenes"]["modified"], ["opening"])
        self.assertFalse(first["published"])
        self.assertFalse(first["reviewed"])
        self.assertEqual(self.flow.inspect(BRIEF["id"])["source_digest"], self.initial)
        self.assertFalse(self.flow.inspect(BRIEF["id"])["reviewed"])
        reviewed = self.flow.review(BRIEF["id"], self.initial, OPERATION, NOTE)
        self.assertEqual(reviewed["source_digest"], first["candidate_digest"])

    def test_preview_rejects_stale_source_and_invalid_edit_without_writes(self):
        for expected, operation, error in (
            ("f" * 64, OPERATION, "stale_source"),
            (self.initial, {"action": "remove_scene", "value": {"id": "opening"}},
             "unknown_choice_source"),
        ):
            with self.subTest(error=error):
                with self.assertRaises(CanonError):
                    self.flow.preview_edit(BRIEF["id"], expected, operation)
                self.assertEqual(self.flow.inspect(BRIEF["id"])["source_digest"], self.initial)
                self.assertFalse(self.flow.inspect(BRIEF["id"])["reviewed"])

    def test_preview_fails_closed_when_writer_lease_is_held(self):
        import os
        fd = self.flow.worlds._directory()
        try:
            self.flow._lock(fd, BRIEF["id"])
            try:
                with self.assertRaises(CanonError) as raised:
                    self.flow.preview_edit(BRIEF["id"], self.initial, OPERATION)
                self.assertEqual(raised.exception.code, "lease_busy")
            finally:
                os.unlink(BRIEF["id"] + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def test_review_approves_exact_published_revision(self):
        result = self.flow.review(BRIEF["id"], self.initial, OPERATION, NOTE)
        self.assertTrue(result["reviewed"])
        inspected = self.flow.inspect(BRIEF["id"])
        self.assertTrue(inspected["reviewed"])
        self.assertEqual(inspected["source_digest"], result["source_digest"])
        self.assertEqual(inspected["world"]["scenes"][0]["title"],
                         "Mira surveys the marsh")
        self.assertNotEqual(result["source_digest"], self.initial)

    def test_stale_digest_does_not_change_source_or_review(self):
        with self.assertRaises(CanonError) as raised:
            self.flow.review(BRIEF["id"], "0" * 64, OPERATION, NOTE)
        self.assertEqual(raised.exception.code, "stale_source")
        inspected = self.flow.inspect(BRIEF["id"])
        self.assertFalse(inspected["reviewed"])
        self.assertEqual(inspected["source_digest"], self.initial)

    def test_second_write_failure_never_approves_new_source(self):
        real_write = self.flow.worlds._write
        calls = 0

        def interrupted(fd, name, data):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated custody failure")
            return real_write(fd, name, data)

        with patch.object(self.flow.worlds, "_write", side_effect=interrupted):
            with self.assertRaises(OSError):
                self.flow.review(BRIEF["id"], self.initial, OPERATION, NOTE)
        inspected = self.flow.inspect(BRIEF["id"])
        self.assertFalse(inspected["reviewed"])
        self.assertNotEqual(inspected["source_digest"], self.initial)
        with self.assertRaises(CanonError) as raised:
            self.flow.compile(BRIEF["id"], inspected["source_digest"])
        self.assertEqual(raised.exception.code, "review_required")

    def test_writer_lock_rejects_concurrent_review_without_mutation(self):
        fd = self.flow.worlds._directory()
        try:
            self.flow._lock(fd, BRIEF["id"])
            try:
                with self.assertRaises(CanonError) as raised:
                    self.flow.review(BRIEF["id"], self.initial, OPERATION, NOTE)
                self.assertEqual(raised.exception.code, "lease_busy")
            finally:
                import os
                os.unlink(BRIEF["id"] + ".lock", dir_fd=fd)
        finally:
            import os
            os.close(fd)
        self.assertEqual(self.flow.inspect(BRIEF["id"])["source_digest"],
                         self.initial)


if __name__ == "__main__":
    unittest.main()
