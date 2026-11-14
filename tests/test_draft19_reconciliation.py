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



class WorkflowSourceCustodyTests(unittest.TestCase):
    """Fail closed when a focused CI command names non-existent or shadowed tests."""

    @staticmethod
    def _step(workflow: str, name: str) -> str:
        marker = "      - name: " + name
        if workflow.count(marker) != 1:
            raise AssertionError("CI step missing or duplicated: " + name)
        return workflow.split(marker, 1)[1].split("      - name:", 1)[0]

    def test_quest_dialogue_focused_paths_are_real_and_have_distinct_modules(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/draft19-gguf-source-qualification.yml").read_text(
            encoding="utf-8"
        )
        step = self._step(workflow, "Qualify collided quest/dialogue pytest module identities")
        selected = [line.strip() for line in step.splitlines()
                    if line.strip().startswith("skeleton/testing/")]
        expected = [
            "skeleton/testing/dialogue_sessions_v1/test_companions_rescue.py",
            "skeleton/testing/questflows_v1/test_questflows_companions_rescue.py",
        ]
        self.assertEqual(selected, expected)
        self.assertEqual(len({Path(path).name for path in selected}), len(selected))
        for path in selected:
            with self.subTest(path=path):
                self.assertTrue((root / path).is_file(), path)
                self.assertFalse((root / path).is_symlink(), path)

    def test_backend_and_root_codeql_test_packages_are_isolated_and_both_required(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/merge-readiness.yml").read_text(
            encoding="utf-8"
        )
        backend = self._step(
            workflow, "Verify tenant-bound binary custody, vault streaming and bounded SSRF"
        )
        source = self._step(
            workflow, "Qualify complete CodeQL alert lineage and cross-package inventory"
        )
        self.assertIn("working-directory: backend", backend)
        self.assertIn("python -m pytest --noconftest -q", backend)
        self.assertIn("python -m pytest --noconftest -q", source)
        self.assertIn("tests/test_codeql_exception_boundary_20261111.py", backend)
        self.assertFalse(backend.rstrip().endswith("\\"), "backend pytest command must terminate")
        for name in (
            "test_full_security_alert_inventory_20261111.py",
            "test_codeql_lineage_contract_20261111.py",
            "test_codeql_all_151_source_contracts_20261111.py",
            "test_codeql_stack_trace_custody_20261111.py",
        ):
            with self.subTest(name=name):
                path = "tests/" + name
                self.assertTrue((root / path).is_file())
                self.assertEqual(source.count(path), 1)
                self.assertNotIn("../" + path, backend)


if __name__ == "__main__":
    unittest.main()
