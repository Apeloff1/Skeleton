"""first_turn: all eight strict source observations without native proof."""
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

class TestAdmission(unittest.TestCase):
    def test_synthetic_source_stages_are_explicitly_not_native(self):
        result = evaluate_domain("first_turn", successful_evidence(STAGE_TYPES))
        self.assertTrue(result.accepted)
        self.assertEqual(tuple(r.stage for r in result.stages), STAGES)
        self.assertFalse(result.to_record()["native_inference_witnessed"])
        self.assertFalse(result.to_record()["physical_device_qualified"])
        self.assertFalse(result.to_record()["release_certified"])

    def test_each_independent_negative_stage_is_still_held(self):
        for stage,case in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=stage):
                result = evaluate_domain("first_turn", case)
                self.assertFalse(result.accepted)
                self.assertIn(stage,[r.stage for r in result.stages if not r.accepted])

    def test_typed_source_contract_inventory(self):
        self.assertEqual(tuple(r["stage"] for r in contracts()), STAGES)
        self.assertEqual(len(contracts()), 8)
