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

    def test_review_can_bind_to_exact_preview_candidate(self):
        preview = self.flow.preview_edit(BRIEF["id"], self.initial, OPERATION)
        result = self.flow.review(
            BRIEF["id"], self.initial, OPERATION, NOTE,
            expected_candidate_digest=preview["candidate_digest"])
        self.assertEqual(result["source_digest"], preview["candidate_digest"])
        self.assertTrue(self.flow.inspect(BRIEF["id"])["reviewed"])

    def test_review_operation_intent_is_source_bound_and_fail_closed(self):
        preview = self.flow.preview_edit(BRIEF["id"], self.initial, OPERATION)
        self.assertEqual(len(preview["operation_digest"]), 64)
        for incorrect in ("0" * 64, "invalid", True):
            with self.subTest(incorrect=incorrect):
                with self.assertRaises(CanonError) as raised:
                    self.flow.review(
                        BRIEF["id"], self.initial, OPERATION, NOTE,
                        expected_candidate_digest=preview["candidate_digest"],
                        expected_operation_digest=incorrect)
                self.assertEqual(raised.exception.code, "review_operation_mismatch")
                self.assertEqual(self.flow.inspect(BRIEF["id"])["source_digest"],
                                 self.initial)
                self.assertFalse(self.flow.inspect(BRIEF["id"])["reviewed"])
        approved = self.flow.review(
            BRIEF["id"], self.initial, OPERATION, NOTE,
            expected_candidate_digest=preview["candidate_digest"],
            expected_operation_digest=preview["operation_digest"])
        self.assertEqual(approved["source_digest"], preview["candidate_digest"])
        self.assertTrue(self.flow.inspect(BRIEF["id"])["reviewed"])

    def test_review_rejects_changed_candidate_before_any_publication(self):
        preview = self.flow.preview_edit(BRIEF["id"], self.initial, OPERATION)
        changed = {
            "action": "replace_scene",
            "value": {"id": "opening", "title": "Unexpected revision",
                      "narrative": "A different change than the preview."},
        }
        for candidate in (preview["candidate_digest"], None, True, "bad"):
            if candidate is None:
                continue
            with self.subTest(candidate=candidate):
                with self.assertRaises(CanonError) as raised:
                    self.flow.review(
                        BRIEF["id"], self.initial, changed, NOTE,
                        expected_candidate_digest=candidate)
                self.assertEqual(raised.exception.code, "review_candidate_mismatch")
                self.assertEqual(
                    self.flow.inspect(BRIEF["id"])["source_digest"], self.initial)
                self.assertFalse(self.flow.inspect(BRIEF["id"])["reviewed"])

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


    def test_prior_approval_cannot_authorize_interrupted_new_revision(self):
        first = self.flow.review(BRIEF["id"], self.initial, OPERATION, NOTE)
        self.assertTrue(self.flow.inspect(BRIEF["id"])["reviewed"])
        second = {
            "action": "replace_scene",
            "value": {
                "id": "opening", "title": "Mira finds a second crossing",
                "narrative": "The safe path changes after the storm.",
            },
        }
        real_write = self.flow.worlds._write
        calls = 0

        def interrupted(fd, name, data):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated review publication failure")
            return real_write(fd, name, data)

        with patch.object(self.flow.worlds, "_write", side_effect=interrupted):
            with self.assertRaises(OSError):
                self.flow.review(BRIEF["id"], first["source_digest"], second, NOTE)
        current = self.flow.inspect(BRIEF["id"])
        self.assertFalse(current["reviewed"])
        self.assertNotEqual(current["source_digest"], first["source_digest"])
        with self.assertRaises(CanonError) as raised:
            self.flow.compile(BRIEF["id"], current["source_digest"])
        self.assertEqual(raised.exception.code, "review_required")
        self.assertEqual(self.flow.diagnose(BRIEF["id"])["next_action"],
                         "review_and_approve_canonical_source")
        approved = self.flow.approve_current(
            BRIEF["id"], current["source_digest"], NOTE)
        self.assertTrue(approved["reviewed"])
        receipt = self.flow.compile(BRIEF["id"], current["source_digest"])
        self.assertEqual(receipt["source_digest"], current["source_digest"])
        self.assertEqual(self.flow.verify(BRIEF["id"]), receipt)

    def test_interrupted_rereview_revokes_previously_compiled_handoff(self):
        """A stale approval cannot preserve an already published playable."""
        first = self.flow.review(BRIEF["id"], self.initial, OPERATION, NOTE)
        before = self.flow.compile(BRIEF["id"], first["source_digest"])
        self.assertEqual(self.flow.verify(BRIEF["id"]), before)

        second = {
            "action": "replace_scene",
            "value": {
                "id": "opening",
                "title": "Storm changes the crossing",
                "narrative": "The original route has been submerged.",
            },
        }
        original_write = self.flow.worlds._write
        writes = 0

        def interrupt_second_publication(fd, name, data):
            nonlocal writes
            writes += 1
            if writes == 2:
                raise OSError("injected review custody interruption")
            return original_write(fd, name, data)

        with patch.object(self.flow.worlds, "_write",
                          side_effect=interrupt_second_publication):
            with self.assertRaises(OSError):
                self.flow.review(
                    BRIEF["id"], first["source_digest"], second, NOTE)

        current = self.flow.inspect(BRIEF["id"])
        self.assertFalse(current["reviewed"])
        self.assertNotEqual(current["source_digest"], first["source_digest"])
        for operation in (
            lambda: self.flow.compile(BRIEF["id"], current["source_digest"]),
            lambda: self.flow.verify(BRIEF["id"]),
            lambda: self.flow.acceptance(BRIEF["id"]),
        ):
            with self.subTest(operation=operation), self.assertRaises(CanonError) as raised:
                operation()
            self.assertEqual(raised.exception.code, "review_required")

        # A stale manual approval must never revive an old digest.
        with self.assertRaises(CanonError) as raised:
            self.flow.approve_current(BRIEF["id"], first["source_digest"], NOTE)
        self.assertEqual(raised.exception.code, "stale_source")
        self.assertFalse(self.flow.inspect(BRIEF["id"])["reviewed"])

        # Explicit current-source approval still does not validate old output.
        self.flow.approve_current(BRIEF["id"], current["source_digest"], NOTE)
        with self.assertRaises(CanonError) as raised:
            self.flow.verify(BRIEF["id"])
        self.assertEqual(raised.exception.code, "laptop_receipt_mismatch")
        after = self.flow.compile(BRIEF["id"], current["source_digest"])
        self.assertEqual(self.flow.verify(BRIEF["id"]), after)
        self.assertNotEqual(after["source_digest"], before["source_digest"])

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

    def test_interrupted_re_review_revokes_prior_approval(self):
        first = self.flow.review(BRIEF["id"], self.initial, OPERATION, NOTE)
        self.flow.compile(BRIEF["id"], first["source_digest"])
        next_operation = {
            "action": "replace_scene",
            "value": {
                "id": "opening", "title": "Mira finds a second route",
                "narrative": "A new trail changes the journey.",
            },
        }
        original_write = self.flow.worlds._write
        writes = 0

        def interrupted(fd, name, data):
            nonlocal writes
            writes += 1
            if writes == 2:
                raise OSError("interrupted review publication")
            return original_write(fd, name, data)

        with patch.object(self.flow.worlds, "_write", side_effect=interrupted):
            with self.assertRaises(OSError):
                self.flow.review(BRIEF["id"], first["source_digest"],
                                 next_operation, NOTE)
        current = self.flow.inspect(BRIEF["id"])
        self.assertFalse(current["reviewed"])
        self.assertNotEqual(current["source_digest"], first["source_digest"])
        with self.assertRaises(CanonError) as raised:
            self.flow.compile(BRIEF["id"], current["source_digest"])
        self.assertEqual(raised.exception.code, "review_required")
        with self.assertRaises(CanonError):
            self.flow.verify(BRIEF["id"])


if __name__ == "__main__":
    unittest.main()
