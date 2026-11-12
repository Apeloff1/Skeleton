"""Adversarial acceptance tests for held 19-source reconciliation ledger.

The source ledger is an inventory, not merge or release permission. Tests must
prove that malformed, missing or reclassified authority cannot pass.
"""
from __future__ import annotations

from copy import deepcopy
import json
from unittest import TestCase

from scripts.check_draft19_reconciliation import (
    AdmissionError,
    LEDGER,
    NUMBERS,
    REQUIRED,
    validate,
)


class Draft19ReconciliationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = json.loads(LEDGER.read_text(encoding="utf-8"))

    def sample(self):
        return deepcopy(self.canonical)

    def assert_denied(self, data, reason):
        with self.assertRaisesRegex(AdmissionError, reason):
            validate(data)

    def test_complete_held_ledger_has_no_release_claim(self):
        result = validate(self.sample())
        self.assertEqual(result["status"], "review_only")
        self.assertEqual(result["sources"], 19)
        self.assertEqual(result["admitted"], 0)
        self.assertFalse(result["remote_ci_verified"])
        self.assertEqual({row["number"] for row in self.canonical["source_prs"]}, NUMBERS)
        self.assertEqual(set(self.canonical["required_gates"]), REQUIRED)

    def test_no_merge_or_release_promotion_without_exact_head_gates(self):
        for key in ("merge_approved", "release_approved"):
            data = self.sample()
            data[key] = True
            with self.subTest(key=key):
                self.assert_denied(data, "security hold removed")

    def test_strict_schema_rejects_unreviewed_authority(self):
        for value in (None, {}, [], "not-an-inventory"):
            with self.subTest(value=type(value).__name__):
                self.assert_denied(value, "schema mismatch")
        data = self.sample()
        data["unreviewed"] = True
        self.assert_denied(data, "schema mismatch")

    def test_missing_gate_cannot_be_hidden(self):
        data = self.sample()
        data["required_gates"].remove("Sealed Context Guard")
        self.assert_denied(data, "mandatory exact-head gates absent")

    def test_baseline_ancestry_must_remain_pinned(self):
        data = self.sample()
        data["baseline_pr"] = 0
        self.assert_denied(data, "unapproved baseline")
        data = self.sample()
        data["baseline_head"] = "0" * 39
        self.assert_denied(data, "invalid SHA")

    def test_incomplete_or_duplicate_source_not_qualified(self):
        data = self.sample()
        data["source_prs"].pop()
        self.assert_denied(data, "19 originals required")
        data = self.sample()
        data["source_prs"][0]["number"] = data["source_prs"][1]["number"]
        self.assert_denied(data, "unauthorized or duplicate PR")

    def test_source_authorization_cannot_be_manufactured(self):
        for flag in ("source_admitted", "merge_approved", "release_approved"):
            data = self.sample()
            data["source_prs"][0][flag] = True
            with self.subTest(flag=flag):
                self.assert_denied(data, "held source admitted")

    def test_quarantine_and_historical_boundaries_are_nonoptional(self):
        for number, classification, message in (
            (5022, "overlap", "quarantine removed"),
            (5038, "overlap", "unwired model code promoted"),
            (4991, "overlap", "historical source promoted"),
        ):
            data = self.sample()
            next(row for row in data["source_prs"] if row["number"] == number)["classification"] = classification
            with self.subTest(source=number):
                self.assert_denied(data, message)

    def test_source_heads_and_file_counts_are_bounded(self):
        data = self.sample()
        data["source_prs"][0]["head_sha"] = "not-a-sha"
        self.assert_denied(data, "invalid source head")
        data = self.sample()
        data["source_prs"][0]["changed_paths"] = -1
        self.assert_denied(data, "invalid file count")


if __name__ == "__main__":
    import unittest

    unittest.main()
