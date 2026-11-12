"""Fail-closed source-ledger admission regressions for the 19 held PRs.

These tests use the real current ledger and never claim merge or remote CI
qualification. Mutations remain in memory; they cannot alter source evidence.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from scripts.check_draft19_reconciliation import AdmissionError, LEDGER, validate


def ledger():
    return json.loads(LEDGER.read_text(encoding="utf-8"))


class Draft19AdmissionTests(unittest.TestCase):
    def test_current_source_ledger_is_review_only(self):
        result = validate(ledger())
        self.assertEqual(result["status"], "review_only")
        self.assertEqual(result["sources"], 19)
        self.assertEqual(result["admitted"], 0)
        self.assertIs(result["remote_ci_verified"], False)

    def test_held_authority_cannot_be_promoted_by_metadata(self):
        for field, unsafe in (
            ("admission", "approved"),
            ("merge_approved", True),
            ("release_approved", True),
            ("baseline_pr", 1),
            ("baseline_head", "invalid-sha"),
        ):
            with self.subTest(field=field):
                candidate = ledger()
                candidate[field] = unsafe
                with self.assertRaises(AdmissionError):
                    validate(candidate)

    def test_missing_or_duplicated_originals_are_denied(self):
        for mode in ("missing", "duplicate", "foreign"):
            with self.subTest(mode=mode):
                candidate = ledger()
                if mode == "missing":
                    candidate["source_prs"].pop()
                elif mode == "duplicate":
                    candidate["source_prs"][1]["number"] = candidate["source_prs"][0]["number"]
                else:
                    candidate["source_prs"][0]["number"] = 999999
                with self.assertRaises(AdmissionError):
                    validate(candidate)

    def test_each_source_requires_explicit_negative_admission(self):
        for key in ("source_admitted", "merge_approved", "release_approved"):
            candidate = ledger()
            candidate["source_prs"][0][key] = True
            with self.subTest(key=key), self.assertRaises(AdmissionError):
                validate(candidate)

    def test_quarantined_unwired_and_historical_disposition_cannot_change(self):
        expectations = {5022: "overlap", 5038: "overlap", 4991: "unwired"}
        for source_number, unsafe in expectations.items():
            candidate = ledger()
            next(s for s in candidate["source_prs"] if s["number"] == source_number)["classification"] = unsafe
            with self.subTest(source_number=source_number), self.assertRaises(AdmissionError):
                validate(candidate)

    def test_required_gates_cannot_be_removed_or_duplicated(self):
        for mode in ("missing", "duplicate", "extra"):
            candidate = ledger()
            if mode == "missing":
                candidate["required_gates"].pop()
            elif mode == "duplicate":
                candidate["required_gates"][0] = candidate["required_gates"][1]
            else:
                candidate["required_gates"].append("Nonexistent Gate")
            with self.subTest(mode=mode), self.assertRaises(AdmissionError):
                validate(candidate)

    def test_unbounded_or_noninteger_source_counts_fail_closed(self):
        for number in (0, -1, 100001, True, "100", None):
            candidate = ledger()
            candidate["source_prs"][0]["changed_paths"] = number
            with self.subTest(number=number), self.assertRaises(AdmissionError):
                validate(candidate)


if __name__ == "__main__":
    unittest.main()
