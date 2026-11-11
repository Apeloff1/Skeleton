"""Adversarial non-release custody tests for the nineteen-PR reconciliation."""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import unittest

from scripts.check_backlog19_actions import Backlog19Hold, parse, validate

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "machine/backlog19_actions_20261108.json"


class Backlog19ActionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = SOURCE.read_bytes()
        cls.data = json.loads(cls.raw)

    def test_frozen_snapshot_is_review_only(self):
        result = parse(self.raw)
        self.assertEqual(result["sources"], 19)
        self.assertEqual(result["classes"]["closed_duplicate"], 4)
        self.assertEqual(result["classes"]["closed_superseded"], 5)
        self.assertEqual(result["classes"]["review_only"], 3)
        self.assertEqual(result["classes"]["held_quarantine"], 2)
        self.assertEqual(result["merged"], 0)
        self.assertEqual(result["status"], "held")
        self.assertIs(result["current_head_ci_verified"], False)

    def test_approval_flags_cannot_be_promoted(self):
        for key in ("merge_approved", "release_approved", "source_admitted",
                    "exact_head_ci_verified"):
            with self.subTest(key=key):
                candidate = deepcopy(self.data)
                candidate["entries"][0][key] = True
                with self.assertRaises(Backlog19Hold):
                    validate(candidate)

    def test_closed_duplicates_require_exact_survivor(self):
        candidate = deepcopy(self.data)
        row = next(x for x in candidate["entries"] if x["number"] == 5056)
        row["survivor_pr"] = 5028
        with self.assertRaises(Backlog19Hold):
            validate(candidate)

    def test_quarantine_cannot_be_promoted_by_snapshot(self):
        candidate = deepcopy(self.data)
        row = next(x for x in candidate["entries"] if x["number"] == 5022)
        row["draft"] = False
        row["disposition"] = "review_only"
        with self.assertRaises(Backlog19Hold):
            validate(candidate)

    def test_stacked_review_cannot_fabricate_release(self):
        candidate = deepcopy(self.data)
        candidate["independent_approval_verified"] = True
        with self.assertRaises(Backlog19Hold):
            validate(candidate)

    def test_duplicate_pr_id_and_weak_sha_denied(self):
        for change in ("duplicate", "sha"):
            with self.subTest(change=change):
                candidate = deepcopy(self.data)
                if change == "duplicate":
                    candidate["entries"][0]["number"] = candidate["entries"][1]["number"]
                else:
                    candidate["entries"][0]["head_sha"] = "0" * 39
                with self.assertRaises(Backlog19Hold):
                    validate(candidate)

    def test_duplicate_json_keys_denied(self):
        with self.assertRaises(Backlog19Hold):
            parse(b'{"schema":"one","schema":"two"}')

    def test_unbounded_and_nonfinite_records_denied(self):
        with self.assertRaises(Backlog19Hold):
            parse(b"x" * (64 * 1024 + 1))
        with self.assertRaises(Backlog19Hold):
            parse(b'{"unexpected":NaN}')


if __name__ == "__main__":
    unittest.main()
