from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "repo_machine_completion",
    ROOT / "skeleton" / "repo_machine" / "completion.py",
)
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)

class RepositoryCompletionTests(unittest.TestCase):
    def test_verified_complete_requires_every_non_compensable_input(self):
        result = M.derive_atomic(
            M.AtomicCompletion(
                implementation_signed=True,
                verification_signed=True,
                required_gates=(True, True),
                hard_dependencies_closed=True,
                evidence_refs=("run://exact-head",),
                evidence_identity_valid=True,
            )
        )
        self.assertEqual(result.state, "verified_complete")

    def test_failed_gate_blocks_even_with_signoff(self):
        result = M.derive_atomic(
            M.AtomicCompletion(
                implementation_signed=True,
                verification_signed=True,
                required_gates=(True, False),
                hard_dependencies_closed=True,
                evidence_refs=("run://exact-head",),
                evidence_identity_valid=True,
            )
        )
        self.assertEqual(result.state, "blocked")
        self.assertIn("failed/missing required gate", result.blockers)

    def test_invalidated_evidence_blocks(self):
        result = M.derive_atomic(
            M.AtomicCompletion(
                implementation_signed=True,
                verification_signed=True,
                required_gates=(True,),
                hard_dependencies_closed=True,
                evidence_refs=("run://old-head",),
                evidence_identity_valid=False,
            )
        )
        self.assertEqual(result.state, "blocked")
        self.assertIn("invalidated evidence identity", result.blockers)

    def test_rollup_never_averages_away_blocker(self):
        self.assertEqual(
            M.rollup(("verified_complete", "blocked", "verified_complete")),
            "blocked",
        )

    def test_change_impact_rejects_noncanonical_paths(self):
        with self.assertRaises(ValueError):
            M.invalidated_by_change(("skeleton\\repo_machine\\x.py",), ("skeleton",))
        with self.assertRaises(ValueError):
            M.invalidated_by_change(("../escape.py",), ("skeleton",))

    def test_change_impact_invalidates_watched_paths(self):
        impacted = M.invalidated_by_change(
            ("skeleton/repo_machine/transaction.py", "docs/readme.md"),
            ("skeleton/repo_machine",),
        )
        self.assertEqual(impacted, ("skeleton/repo_machine/transaction.py",))


if __name__ == "__main__":
    unittest.main()
