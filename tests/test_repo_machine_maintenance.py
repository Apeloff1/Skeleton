from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "repo_machine_maintenance",
    ROOT / "skeleton" / "repo_machine" / "maintenance.py",
)
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)

class RepositoryMaintenanceTests(unittest.TestCase):
    def _assessment(self, **changes):
        values = dict(
            path="tmp/obsolete.txt",
            owner_resolved=True,
            trace_reachable=False,
            retention_hold=False,
            migration_safe=True,
            regeneration_authority="generator://tmp",
            rollback_ref="git://abc123",
            owner_evidence_ref="owner://tmp",
            trace_evidence_ref="trace://tmp",
            retention_evidence_ref="retention://tmp",
            migration_evidence_ref="migration://tmp",
            protected_paths=("machine", "docs/adr"),
        )
        values.update(changes)
        return M.DeletionAssessment(**values)

    def test_maintenance_text_fields_do_not_coerce(self):
        with self.assertRaises(TypeError):
            self._assessment(path=123)
        with self.assertRaises(TypeError):
            self._assessment(regeneration_authority=True)

    def test_safe_candidate_requires_all_checks(self):
        decision = M.evaluate_deletion(self._assessment())
        self.assertTrue(decision.allowed)
        self.assertEqual(len(decision.checks), 6)
        self.assertEqual(len(decision.evidence_refs), 5)

    def test_protected_path_is_blocked(self):
        decision = M.evaluate_deletion(self._assessment(path="machine/control.json"))
        self.assertFalse(decision.allowed)
        self.assertIn("protected path", decision.blockers)

    def test_live_trace_reachability_is_blocked(self):
        decision = M.evaluate_deletion(self._assessment(trace_reachable=True))
        self.assertFalse(decision.allowed)
        self.assertIn("live trace reachability", decision.blockers)

    def test_retention_hold_and_migration_block(self):
        decision = M.evaluate_deletion(
            self._assessment(retention_hold=True, migration_safe=False)
        )
        self.assertFalse(decision.allowed)
        self.assertIn("retention/evidence hold", decision.blockers)
        self.assertIn("migration/cutover unsafe", decision.blockers)

    def test_core_control_paths_are_always_protected(self):
        decision = M.evaluate_deletion(
            self._assessment(path=".github/workflows/ci.yml", protected_paths=())
        )
        self.assertFalse(decision.allowed)
        self.assertIn("protected path", decision.blockers)

    def test_missing_check_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            self._assessment(trace_evidence_ref="")

    def test_overlapping_batch_candidates_are_rejected(self):
        parent = self._assessment(path="tmp/pkg")
        child = self._assessment(path="tmp/pkg/file.txt")
        with self.assertRaisesRegex(M.MaintenancePolicyError, "overlapping"):
            M.evaluate_batch((parent, child))

    def test_duplicate_batch_candidate_is_rejected(self):
        item = self._assessment()
        with self.assertRaises(M.MaintenancePolicyError):
            M.evaluate_batch((item, item))


if __name__ == "__main__":
    unittest.main()
