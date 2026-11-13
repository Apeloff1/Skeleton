"""first_turn: independently accepted stages may still contradict each other."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import (
    successful_evidence, mutation_cases,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.first_turn.registry import (
    STAGES, STAGE_TYPES, contracts,
)

class TestCoherence(unittest.TestCase):
    def test_normal_source_only_stage_fixture_is_consistent(self):
        result = evaluate_domain("first_turn", successful_evidence(STAGE_TYPES))
        self.assertTrue(result.accepted)
        self.assertFalse(result.to_record()["release_certified"])

    def test_cross_stage_mismatch_denied_without_side_effects(self):
        e = successful_evidence(STAGE_TYPES)
        e["generation_reservation"]["reserved"] = 4096
        with self.assertRaisesRegex(LaptopGateHold, "contradiction"):
            evaluate_domain("first_turn", e)

    def test_single_negative_stage_retains_its_typed_denial(self):
        stage,case = mutation_cases(STAGE_TYPES)[0]
        result = evaluate_domain("first_turn", case)
        self.assertFalse(result.accepted)
        self.assertIn(stage,[x.stage for x in result.stages if not x.accepted])
