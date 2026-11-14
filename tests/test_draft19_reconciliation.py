"""Adversarial held-source ledger regression; no merge or release grants."""
from __future__ import annotations

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
    unittest.main()
