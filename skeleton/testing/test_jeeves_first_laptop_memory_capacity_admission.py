"""All memory-capacity safeguards are required for positive source diagnostics."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.memory_capacity.registry import STAGES, STAGE_TYPES, contracts

class TestMemoryAdmission(unittest.TestCase):
    def test_complete_diagnostic_never_claims_physical_proof(self):
        v = evaluate_domain("memory_capacity", successful_evidence(STAGE_TYPES))
        self.assertTrue(v.accepted)
        self.assertEqual(tuple(s.stage for s in v.stages), STAGES)
        self.assertFalse(v.to_record()["native_inference_witnessed"])
        self.assertFalse(v.to_record()["physical_device_qualified"])

    def test_each_failing_stage_holds_entire_domain(self):
        for stage, fixture in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=stage):
                v = evaluate_domain("memory_capacity", fixture)
                self.assertFalse(v.accepted)
                self.assertEqual([s.stage for s in v.stages if not s.accepted], [stage])
