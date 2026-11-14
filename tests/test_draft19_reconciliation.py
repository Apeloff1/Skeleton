"""Adversarial held-source ledger regression; no merge or release grants."""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

from scripts.check_draft19_reconciliation import (
    AdmissionError, KIND, LEDGER, NUMBERS, REQUIRED, validate,
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


class Draft19SourceAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.canonical = json.loads(LEDGER.read_text(encoding="utf-8"))

    def mutation(self, change, label: str) -> None:
        candidate = deepcopy(self.canonical)
        change(candidate)
        with self.subTest(case=label):
            with self.assertRaises(AdmissionError):
                validate(candidate)

    def test_canonical_19_sources_are_review_only_and_all_held(self):
        result = validate(deepcopy(self.canonical))
        self.assertEqual(result["sources"], 19)
        self.assertEqual(result["admitted"], 0)
        self.assertEqual(result["status"], "review_only")
        self.assertFalse(result["remote_ci_verified"])
        self.assertEqual(set(result["classes"]), set(KIND))
        self.assertEqual(len({entry["number"] for entry in self.canonical["source_prs"]}), 19)
        self.assertEqual({entry["number"] for entry in self.canonical["source_prs"]}, NUMBERS)

    def test_untrusted_top_level_admission_and_release_cannot_change(self):
        self.mutation(lambda d: d.update(admission="source_admitted"), "admission")
        self.mutation(lambda d: d.update(merge_approved=True), "merge")
        self.mutation(lambda d: d.update(release_approved=True), "release")
        self.mutation(lambda d: d.update(owner="unapproved/repository"), "owner")
        self.mutation(lambda d: d.update(baseline_pr=5324), "baseline")
        self.mutation(lambda d: d.update(schema="unknown"), "schema")
        self.mutation(lambda d: d.update(extra=True), "unknown-key")

    def test_every_required_security_and_source_gate_remains_mandatory(self):
        self.assertEqual(set(self.canonical["required_gates"]), REQUIRED)
        for gate in REQUIRED:
            self.mutation(lambda d, g=gate: d["required_gates"].remove(g), "removed:" + gate)
        self.mutation(lambda d: d["required_gates"].append("unknown gate"), "extra-gate")
        self.mutation(lambda d: d.__setitem__("required_gates", sorted(REQUIRED)[:-1] + [True]), "non-text")
        self.mutation(lambda d: d.__setitem__("required_gates", []), "empty")

    def test_source_inventory_is_unique_complete_and_exactly_19(self):
        self.mutation(lambda d: d["source_prs"].pop(), "missing-source")
        self.mutation(lambda d: d["source_prs"].append(deepcopy(d["source_prs"][0])), "extra-source")
        self.mutation(lambda d: d["source_prs"][0].update(number=d["source_prs"][1]["number"]), "duplicate")
        self.mutation(lambda d: d["source_prs"][0].update(number=999999), "unknown-source")
        self.mutation(lambda d: d["source_prs"][0].update(head_sha="0" * 39), "short-sha")
        self.mutation(lambda d: d["source_prs"][0].update(head_sha="z" * 40), "invalid-sha")
        self.mutation(lambda d: d["source_prs"][0].update(changed_paths=0), "empty-source")
        self.mutation(lambda d: d["source_prs"][0].update(changed_paths=True), "boolean-count")
        self.mutation(lambda d: d["source_prs"][0].update(changed_paths=100001), "unbounded-count")

    def test_each_original_source_retains_all_three_independent_holds(self):
        for index in range(19):
            for field in ("source_admitted", "merge_approved", "release_approved"):
                self.mutation(
                    lambda d, i=index, f=field: d["source_prs"][i].__setitem__(f, True),
                    f"{index}:{field}",
                )

    def test_quarantined_unwired_and_historical_sources_cannot_be_promoted(self):
        for number, expected_kind in ((5022, "quarantine"), (5038, "unwired"), (4991, "historical")):
            original = next(x for x in self.canonical["source_prs"] if x["number"] == number)
            self.assertEqual(original["classification"], expected_kind)
            self.mutation(
                lambda d, n=number: next(
                    x for x in d["source_prs"] if x["number"] == n
                ).__setitem__("classification", "overlap"),
                f"promotion:{number}",
            )

    def test_schema_and_source_fields_fail_closed_on_unknown_payloads(self):
        self.mutation(lambda d: d["source_prs"][0].update(merge_override="yes"), "new-source-flag")
        self.mutation(lambda d: d["source_prs"][0].pop("source_admitted"), "missing-source-flag")
        self.mutation(lambda d: d.__setitem__("baseline_head", "not-a-sha"), "unqualified-base")
        self.mutation(lambda d: d["source_prs"][0].__setitem__("classification", "approved"), "unsafe-kind")


if __name__ == "__main__":
    unittest.main()
