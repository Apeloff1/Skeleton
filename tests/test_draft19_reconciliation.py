"""Reconciled independent source-custody regressions from Jeeves and Dragon.

Artificial artifact fixtures never establish native model or release qualification.
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


# Independent Dragon donor cases retained during integration.
from copy import deepcopy
import json
import unittest

from scripts.check_draft19_reconciliation import (
    AdmissionError, LEDGER, NUMBERS, REQUIRED, validate,
)


class Draft19HeldSourceQualification(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(LEDGER.read_text(encoding="utf-8"))

    def rejects(self, mutation):
        candidate = deepcopy(self.manifest)
        mutation(candidate)
        with self.assertRaises(AdmissionError):
            validate(candidate)

    def test_complete_19_source_manifest_remains_review_only(self):
        result = validate(deepcopy(self.manifest))
        self.assertEqual(result["sources"], 19)
        self.assertEqual(result["admitted"], 0)
        self.assertFalse(result["remote_ci_verified"])
        self.assertEqual(result["status"], "review_only")
        self.assertEqual(set(item["number"] for item in self.manifest["source_prs"]), NUMBERS)
        self.assertEqual(set(self.manifest["required_gates"]), REQUIRED)
        self.assertEqual(sum(result["classes"].values()), 19)

    def test_replay_cannot_claim_merge_or_release_authority(self):
        for key in ("merge_approved", "release_approved"):
            with self.subTest(key=key):
                self.rejects(lambda d: d.__setitem__(key, True))
        self.rejects(lambda d: d.__setitem__("admission", "release"))
        self.rejects(lambda d: d.__setitem__("admission", "approved"))
        self.rejects(lambda d: d["source_prs"][0].__setitem__("source_admitted", True))
        self.rejects(lambda d: d["source_prs"][0].__setitem__("merge_approved", True))
        self.rejects(lambda d: d["source_prs"][0].__setitem__("release_approved", True))

    def test_required_security_checks_cannot_be_dropped_or_duplicated(self):
        self.rejects(lambda d: d["required_gates"].remove("Sealed Context Guard"))
        self.rejects(lambda d: d["required_gates"].append("Unsupported"))
        self.rejects(lambda d: d["required_gates"].__setitem__(0, d["required_gates"][1]))
        self.rejects(lambda d: d.__setitem__("required_gates", "all-green"))

    def test_original_source_inventory_is_exact_and_unique(self):
        self.rejects(lambda d: d["source_prs"].pop())
        self.rejects(lambda d: d["source_prs"][0].__setitem__(
            "number", d["source_prs"][1]["number"]
        ))
        self.rejects(lambda d: d["source_prs"][0].__setitem__("number", True))
        self.rejects(lambda d: d["source_prs"][0].__setitem__("number", 999999))
        self.rejects(lambda d: d["source_prs"][0].__setitem__("changed_paths", 0))
        self.rejects(lambda d: d["source_prs"][0].__setitem__("changed_paths", 100001))

    def test_exception_dispositions_remain_pinned(self):
        index = {item["number"]: i for i, item in enumerate(self.manifest["source_prs"])}
        for number in (5022, 5038, 4991):
            i = index[number]
            with self.subTest(number=number):
                self.rejects(lambda d, j=i: d["source_prs"][j].__setitem__("classification", "overlap"))
        self.rejects(lambda d: d["source_prs"][0].__setitem__("classification", "accepted"))

    def test_baseline_and_source_sha_are_not_user_supplied_authority(self):
        self.rejects(lambda d: d.__setitem__("baseline_pr", 5281))
        self.rejects(lambda d: d.__setitem__("baseline_head", "a" * 39))
        self.rejects(lambda d: d.__setitem__("baseline_head", "A" * 40))
        self.rejects(lambda d: d["source_prs"][0].__setitem__("head_sha", "A" * 40))
        self.rejects(lambda d: d["source_prs"][0].__setitem__("head_sha", "0" * 39))
        self.rejects(lambda d: d.__setitem__("owner", "foreign/repo"))

    def test_unknown_manifest_fields_cannot_be_forged(self):
        self.rejects(lambda d: d.__setitem__("remote_ci_verified", True))
        self.rejects(lambda d: d["source_prs"][0].__setitem__("override", True))


if __name__ == "__main__":
    import unittest
    unittest.main()
