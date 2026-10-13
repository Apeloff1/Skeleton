from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_ai_phase_inheritance",
    ROOT / "scripts" / "verify_ai_phase_inheritance.py",
)
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)


FILES = (
    "machine/ai_app_construction.json",
    "machine/ai_closure_evidence.json",
    "machine/ai_implementation_handoff.json",
    "machine/ai_p1_terminal_closure.json",
    "machine/ai_p2_functional_ai_closure.json",
    "machine/ai_p2_execution_map.json",
    "machine/ai_p2_task_backlog.json",
    "machine/ai_build_queue.json",
)


def docs() -> dict[str, dict]:
    return {
        path: json.loads((ROOT / path).read_text(encoding="utf-8"))
        for path in FILES
    }


class PhaseInheritanceVerifierTests(unittest.TestCase):
    def verify_docs(self, values: dict[str, dict]) -> dict:
        frozen = copy.deepcopy(values)

        def fake_load(_root, relative):
            return copy.deepcopy(frozen[relative])

        with patch.object(M, "_load", side_effect=fake_load):
            return M.verify(ROOT, head_sha="a" * 40)

    def test_repository_phase_chain_is_valid(self) -> None:
        receipt = M.verify(ROOT, head_sha="b" * 40)
        self.assertTrue(receipt["valid"], receipt["errors"])
        self.assertEqual(receipt["head_sha"], "b" * 40)
        self.assertEqual(
            receipt["atomic_accountability_queue"]["role"],
            "construction/signoff ledger; not terminal phase-closure authority",
        )

    def test_pending_atomic_queue_does_not_reopen_terminal_phase_claims(self) -> None:
        values = docs()
        values["machine/ai_build_queue.json"]["tasks"][0]["status"] = "pending"
        receipt = self.verify_docs(values)
        self.assertTrue(receipt["valid"], receipt["errors"])
        self.assertGreater(
            receipt["atomic_accountability_queue"]["status_counts"].get("pending", 0),
            0,
        )

    def test_p1_terminal_reopen_breaks_inheritance(self) -> None:
        values = docs()
        values["machine/ai_p1_terminal_closure.json"]["status"] = "active"
        receipt = self.verify_docs(values)
        self.assertFalse(receipt["valid"])
        self.assertIn("P1 terminal closure is not closed", receipt["errors"])

    def test_p2_partition_drift_breaks_inheritance(self) -> None:
        values = docs()
        values["machine/ai_p2_functional_ai_closure.json"]["source_scope"][
            "queued_volume_count"
        ] = 256
        receipt = self.verify_docs(values)
        self.assertFalse(receipt["valid"])
        self.assertIn("P2 queued volume count must remain 257", receipt["errors"])

    def _functional_task(self, values: dict[str, dict]) -> dict:
        return next(
            row for row in values["machine/ai_p2_task_backlog.json"]["tasks"]
            if row["task_id"] == "P2-T1-FUNCTIONAL-01"
        )

    def test_signed_functional_task_closure_requires_workflow_evidence(self) -> None:
        values = docs()
        task = self._functional_task(values)
        self.assertEqual(task["status"], "closed")
        self.assertTrue(task["implementation_signed"])
        self.assertTrue(task["verification_signed"])
        receipt = self.verify_docs(values)
        self.assertTrue(receipt["valid"], receipt["errors"])

    def test_unpromoted_task_still_permitted_without_self_signing(self) -> None:
        values = docs()
        task = self._functional_task(values)
        task["status"] = "landed_unpromoted"
        task["completion_checkbox"] = False
        task["completion_checkbox_mark"] = "[ ]"
        task["implementation_signed"] = False
        task["verification_signed"] = False
        receipt = self.verify_docs(values)
        self.assertTrue(receipt["valid"], receipt["errors"])

    def test_p2_task_cannot_self_promote(self) -> None:
        values = docs()
        task = self._functional_task(values)
        task["verification_signed"] = False
        receipt = self.verify_docs(values)
        self.assertFalse(receipt["valid"])
        self.assertIn(
            "P2-T1-FUNCTIONAL-01 closed task requires completed, signed evidence",
            receipt["errors"],
        )

    def test_self_signed_unpromoted_task_rejected(self) -> None:
        values = docs()
        task = self._functional_task(values)
        task["status"] = "landed_unpromoted"
        task["completion_checkbox"] = False
        task["completion_checkbox_mark"] = "[ ]"
        task["implementation_signed"] = False
        task["verification_signed"] = True
        receipt = self.verify_docs(values)
        self.assertFalse(receipt["valid"])
        self.assertIn(
            "P2-T1-FUNCTIONAL-01 unpromoted task must keep verification_signed false",
            receipt["errors"],
        )

    def test_closed_task_rejects_missing_acceptance_workflow(self) -> None:
        values = docs()
        task = self._functional_task(values)
        task["evidence_refs"] = [
            ref for ref in task["evidence_refs"]
            if not ref.startswith("workflow:P2 Functional AI Acceptance@")
        ]
        receipt = self.verify_docs(values)
        self.assertFalse(receipt["valid"])
        self.assertIn(
            "P2-T1-FUNCTIONAL-01 lacks pinned independent acceptance evidence",
            receipt["errors"],
        )

    def test_closed_task_rejects_unpinned_workflow(self) -> None:
        values = docs()
        task = self._functional_task(values)
        task["evidence_refs"] = [
            ref.replace("@c6e966454b6ecb1b2a8d8fe51ce3f752c507f29f:", "@"
                        + "0" * 40 + ":")
            if ref.startswith("workflow:P2 Functional AI Acceptance@") else ref
            for ref in task["evidence_refs"]
        ]
        receipt = self.verify_docs(values)
        self.assertFalse(receipt["valid"])
        self.assertIn(
            "P2-T1-FUNCTIONAL-01 lacks pinned independent acceptance evidence",
            receipt["errors"],
        )

    def test_closed_task_rejects_missing_action_run(self) -> None:
        values = docs()
        task = self._functional_task(values)
        task["evidence_refs"] = [
            ref for ref in task["evidence_refs"]
            if not ref.startswith("github-actions-run:")
        ]
        receipt = self.verify_docs(values)
        self.assertFalse(receipt["valid"])
        self.assertIn(
            "P2-T1-FUNCTIONAL-01 lacks pinned independent acceptance evidence",
            receipt["errors"],
        )

    def test_closed_task_rejects_duplicate_evidence(self) -> None:
        values = docs()
        task = self._functional_task(values)
        task["evidence_refs"].append(task["evidence_refs"][0])
        receipt = self.verify_docs(values)
        self.assertFalse(receipt["valid"])
        self.assertIn(
            "P2-T1-FUNCTIONAL-01 evidence references must be unique non-empty text",
            receipt["errors"],
        )


if __name__ == "__main__":
    unittest.main()
