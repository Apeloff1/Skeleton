"""signed_sources: all eight strict stages and full negative mutation matrix."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.signed_sources.registry import STAGES, STAGE_TYPES, contracts

class TestAdmission(unittest.TestCase):
    def test_complete_source_fixture_does_not_prove_hardware(self):
        result = evaluate_domain("signed_sources", successful_evidence(STAGE_TYPES))
        self.assertTrue(result.accepted)
        self.assertEqual(tuple(v.stage for v in result.stages), STAGES)
        self.assertFalse(result.to_record()["native_inference_witnessed"])
        self.assertFalse(result.to_record()["physical_device_qualified"])
        self.assertFalse(result.to_record()["release_certified"])

    def test_every_stage_can_independently_deny(self):
        for stage, fixture in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=stage):
                result = evaluate_domain("signed_sources", fixture)
                self.assertFalse(result.accepted)
                self.assertIn(stage, [x.stage for x in result.stages if not x.accepted])
