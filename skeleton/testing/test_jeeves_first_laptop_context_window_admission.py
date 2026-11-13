"""Context window acceptance requires eight checks and a coherent budget."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.context_window.registry import STAGES, STAGE_TYPES, contracts

class TestContextAdmission(unittest.TestCase):
    def test_all_source_stages_admitted_without_hardware_claim(self):
        verdict = evaluate_domain("context_window", successful_evidence(STAGE_TYPES))
        self.assertTrue(verdict.accepted)
        self.assertEqual(tuple(x.stage for x in verdict.stages), STAGES)
        self.assertFalse(verdict.to_record()["native_inference_witnessed"])
        self.assertFalse(verdict.to_record()["release_certified"])

    def test_negative_stage_denies_entire_domain(self):
        for stage, fixture in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=stage):
                report = evaluate_domain("context_window", fixture)
                self.assertFalse(report.accepted)
                self.assertIn(stage, [v.stage for v in report.stages if not v.accepted])
