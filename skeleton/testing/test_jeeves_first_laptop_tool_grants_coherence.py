"""tool_grants: cross-stage aggregate reservations must not be bypassed."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import (
    successful_evidence, mutation_cases,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.tool_grants.registry import (
    STAGES, STAGE_TYPES, contracts,
)

class TestCoherence(unittest.TestCase):
    def test_normal_synthetic_fixture_has_coherent_budget(self):
        self.assertTrue(
            evaluate_domain("tool_grants", successful_evidence(STAGE_TYPES)).accepted
        )

    def test_individually_legal_claims_can_conflict_in_aggregate(self):
        e = successful_evidence(STAGE_TYPES)
        e["grant_capacity"]["reserved"] = 1
        with self.assertRaisesRegex(LaptopGateHold, "contradictory"):
            evaluate_domain("tool_grants", e)

    def test_negative_individual_stage_keeps_explicit_typed_denial(self):
        stage, case = mutation_cases(STAGE_TYPES)[0]
        verdict = evaluate_domain("tool_grants", case)
        self.assertIn(stage, [s.stage for s in verdict.stages if not s.accepted])
        self.assertFalse(verdict.accepted)

    def test_oversized_values_fail_even_if_other_stage_would_deny(self):
        e = successful_evidence(STAGE_TYPES)
        e[STAGES[0]][next(iter(e[STAGES[0]]))] = 10**16
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("tool_grants", e)
