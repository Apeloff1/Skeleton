from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "repo_machine_priority",
    ROOT / "skeleton" / "repo_machine" / "priority.py",
)
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)

class RepositoryPriorityTests(unittest.TestCase):
    def test_hard_blocker_dominates_soft_score(self):
        hard = M.decide_priority(
            "A",
            blockers=(M.HardBlocker("required-gate", 1000),),
            soft_factors={"risk": -100},
        )
        soft = M.decide_priority("B", soft_factors={"risk": 100})
        self.assertLess(hard.sort_key, soft.sort_key)

    def test_anti_starvation_forces_review(self):
        decision = M.decide_priority(
            "A",
            soft_factors={"risk": 0},
            wait_cycles=20,
            max_soft_wait_cycles=20,
        )
        self.assertTrue(decision.forced_review)

    def test_completion_percentage_is_not_priority_input(self):
        with self.assertRaises(M.PriorityPolicyError):
            M.decide_priority("A", soft_factors={"completion_percent": 90})

    def test_soft_factor_flood_is_rejected(self):
        with self.assertRaisesRegex(M.PriorityPolicyError, "too many soft"):
            M.decide_priority(
                "A",
                soft_factors={f"factor-{i}": 1 for i in range(17)},
            )

    def test_priority_counters_reject_bool_and_float(self):
        with self.assertRaises(TypeError):
            M.decide_priority("A", wait_cycles=True)
        with self.assertRaises(TypeError):
            M.decide_priority("A", age_sequence=1.5)

    def test_duplicate_hard_blocker_identity_is_rejected(self):
        blocker = M.HardBlocker("required-gate", 1000)
        with self.assertRaisesRegex(M.PriorityPolicyError, "duplicate hard blocker"):
            M.decide_priority("A", blockers=(blocker, blocker))

    def test_soft_factor_must_stay_bounded(self):
        with self.assertRaises(M.PriorityPolicyError):
            M.decide_priority(
                "A",
                soft_factors={"risk": 101},
                factor_bounds={"risk": (0, 100)},
            )


if __name__ == "__main__":
    unittest.main()
