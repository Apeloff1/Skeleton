"""Exact-source multi-file patch proposals: all-or-nothing read-only review."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import unittest

from skeleton.ai.game_builder.jeeves_appwide_fabric import (
    AppwideInventory, JeevesAppwideError, JeevesAppwideRuntime)
from skeleton.ai.game_builder.jeeves_source_patchset import (
    _compile_edits, preview_source_patchset)
from tests.test_game_builder_jeeves_completion_census import CompletionCensusTests


class SourcePatchsetReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CompletionCensusTests(
            "test_sources_and_declared_maturity_never_certify_product")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.inv = self.fixture.inv
        self.a = "skeleton/ai/game_builder/one.py"
        self.b = "skeleton/ai/game_builder/two.py"
        self.original_a = "def one():\n    return 'old_value'\n"
        self.original_b = "def two():\n    return 10\n"
        self.fixture.put(self.a, self.original_a)
        self.fixture.put(self.b, self.original_b)
        self.inv.scan()
        self.reason = "Refactor two original game controls with exact ownership proof."
        self.patches = [
            {"path": self.a,
             "expected_sha256": sha256(self.original_a.encode()).hexdigest(),
             "edits": [{"old": "old_value", "new": "new_value"}]},
            {"path": self.b,
             "expected_sha256": sha256(self.original_b.encode()).hexdigest(),
             "edits": [{"old": "return 10", "new": "return 11"}]},
        ]

    def preview(self, **extra):
        return preview_source_patchset(
            self.inv, patches=self.patches, reason=self.reason,
            operator_authorized=True, **extra)

    def test_two_file_exact_review_is_deterministic_and_mutates_nothing(self):
        before = (self.inv.root / self.a).read_bytes()
        after = (self.inv.root / self.b).read_bytes()
        receipt = self.preview(expected_snapshot=self.inv._digest)
        self.assertEqual(receipt["file_count"], 2)
        self.assertEqual(receipt["hunk_count"], 2)
        self.assertTrue(receipt["all_paths_preflighted_before_review"])
        self.assertTrue(receipt["every_edit_matched_unique_unchanged_source"])
        self.assertEqual(receipt["source_files_written"], 0)
        self.assertEqual(receipt["commits_created"], 0)
        self.assertEqual(receipt["tests_run"], 0)
        self.assertTrue(receipt["review_and_independent_authorization_required"])
        self.assertEqual(receipt, self.preview())
        self.assertEqual(before, (self.inv.root / self.a).read_bytes())
        self.assertEqual(after, (self.inv.root / self.b).read_bytes())
        self.assertTrue(all(p["source_committed"] is False
                            for p in receipt["patches"]))

    def test_unapproved_patchset_is_never_proposed(self):
        runtime = JeevesAppwideRuntime(self.inv)
        with self.assertRaises(PermissionError):
            runtime.invoke("source.patchset.preview", {
                "patches": self.patches, "reason": self.reason})
        approved = runtime.invoke("source.patchset.preview", {
            "patches": self.patches, "reason": self.reason},
            authorized=True)
        self.assertEqual(approved["result"]["hunk_count"], 2)
        self.assertEqual(approved["result"]["source_files_written"], 0)

    def test_stale_one_file_refuses_entire_batch(self):
        original = (self.inv.root / self.a).read_bytes()
        self.patches[1]["expected_sha256"] = "0" * 64
        with self.assertRaises(JeevesAppwideError):
            self.preview()
        self.assertEqual((self.inv.root / self.a).read_bytes(), original)
        self.assertFalse((self.inv.root / self.b).read_bytes() !=
                         self.original_b.encode())

    def test_equal_length_stale_edit_not_accepted(self):
        self.fixture.put(self.a, self.original_a.replace("old_value", "old_walue"))
        self.inv.scan()
        with self.assertRaises(JeevesAppwideError):
            self.preview()

    def test_rejects_ambiguous_overlapping_or_synthesized_hunks(self):
        unchanged = "alpha beta alpha gamma"
        with self.assertRaises(JeevesAppwideError):
            _compile_edits(unchanged, [{"old": "alpha", "new": "omega"}],
                           path="example.py")
        with self.assertRaises(JeevesAppwideError):
            _compile_edits(
                "hello unique world",
                [{"old": "hello unique", "new": "x"},
                 {"old": "unique world", "new": "y"}],
                path="example.py")
        with self.assertRaises(JeevesAppwideError):
            _compile_edits("abc", [{"old": "a", "new": "a"}], path="example.py")
        with self.assertRaises(JeevesAppwideError):
            _compile_edits("abc", [{"old": "z", "new": "x"}], path="example.py")

    def test_unicode_offsets_do_not_corrupt_source(self):
        original = "Æ character\nCafé script\n"
        proposed, details = _compile_edits(
            original, [{"old": "Café", "new": "Über"}], path="source.py")
        self.assertEqual(proposed, "Æ character\nÜber script\n")
        self.assertEqual(details[0]["original_line"], 2)
        self.assertEqual(details[0]["old_bytes"], len("Café".encode()))
        self.assertEqual(details[0]["new_bytes"], len("Über".encode()))

    def test_duplicate_target_or_out_of_root_or_private_path_denied(self):
        for corrupted in (
            [deepcopy(self.patches[0]), deepcopy(self.patches[0])],
            [{"path": "../../etc/passwd",
              "expected_sha256": "0"*64, "edits": [{"old":"x","new":"y"}]}],
            [{"path": "machine/.env",
              "expected_sha256": "0"*64, "edits": [{"old":"x","new":"y"}]}],
        ):
            with self.subTest(corrupted=corrupted), self.assertRaises(
                JeevesAppwideError):
                preview_source_patchset(
                    self.inv, patches=corrupted,
                    reason=self.reason, operator_authorized=True)

    def test_boolean_parameters_and_budgets_rejected(self):
        for bad in ([], [True], [1], [{}], [self.patches[0]]*9):
            with self.subTest(bad=bad), self.assertRaises(JeevesAppwideError):
                preview_source_patchset(
                    self.inv, patches=bad, reason=self.reason,
                    operator_authorized=True)
        with self.assertRaises(PermissionError):
            preview_source_patchset(
                self.inv, patches=self.patches, reason=self.reason,
                operator_authorized=False)

    def test_optimistic_inventory_cursor_blocks_outdated_review(self):
        with self.assertRaises(JeevesAppwideError):
            self.preview(expected_snapshot="0"*64)


if __name__ == "__main__":
    unittest.main()
