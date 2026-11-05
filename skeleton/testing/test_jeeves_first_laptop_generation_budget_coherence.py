"""generation_budget: individually accepted stages must also agree across stages."""
from __future__ import annotations
import unittest

from skeleton.jeeves.native_fabric.laptop_ops.casebook import (
    successful_evidence, mutation_cases,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.generation_budget.registry import (
    STAGES, STAGE_TYPES, contracts,
)

class CoherenceTests(unittest.TestCase):
    def test_baseline_cross_stage_consistency(self):
        result = evaluate_domain("generation_budget", successful_evidence(STAGE_TYPES))
        self.assertTrue(result.accepted)
        self.assertIs(result.to_record()["release_certified"], False)

    def test_independently_valid_observations_can_still_conflict(self):
        e = successful_evidence(STAGE_TYPES)
        e["model_calls"]["used"] = 8; e["per_call_tokens"]["used"] = 8; e["total_tokens"].update({"available": 32, "reserved": 16})
        with self.assertRaisesRegex(LaptopGateHold, "contradictory"):
            evaluate_domain("generation_budget", e)

    def test_stage_failure_stays_explicit_in_verdict(self):
        name, case = mutation_cases(STAGE_TYPES)[0]
        result = evaluate_domain("generation_budget", case)
        self.assertFalse(result.accepted)
        self.assertIn(name, [s.stage for s in result.stages if not s.accepted])
