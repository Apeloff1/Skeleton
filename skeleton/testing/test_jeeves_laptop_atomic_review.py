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

    def test_interrupted_reversion_cannot_replay_prior_approval(self):
        first = self.flow.review(BRIEF["id"], self.initial, OPERATION, NOTE)
        prior_digest = first["source_digest"]
        revert = {
            "action": "replace_scene",
            "value": {
                "id": "opening", "title": "Mira in North Marsh",
                "narrative": BRIEF["premise"],
            },
        }
        second = self.flow.review(BRIEF["id"], prior_digest, revert, NOTE)
        self.assertEqual(second["source_digest"], self.initial)
        # The earlier reviewed revision still exists in the source history.
        # Simulate interruption while attempting to restore that digest.
        real_write = self.flow.worlds._write
        calls = 0

        def interrupted(fd, name, data):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("interrupted approval publication")
            return real_write(fd, name, data)

        with patch.object(self.flow.worlds, "_write", side_effect=interrupted):
            with self.assertRaises(OSError):
                self.flow.review(BRIEF["id"], self.initial, OPERATION, NOTE)
        inspected = self.flow.inspect(BRIEF["id"])
        self.assertEqual(inspected["source_digest"], prior_digest)
        self.assertFalse(inspected["reviewed"])
        with self.assertRaises(CanonError) as raised:
            self.flow.compile(BRIEF["id"], prior_digest)
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
