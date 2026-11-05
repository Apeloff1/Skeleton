"""gpu_admission complete eight-stage, non-authoritative source admission."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.gpu_admission.registry import STAGES, STAGE_TYPES, contracts

class AdmissionTests(unittest.TestCase):
    def test_complete_eight_stages_never_certify_real_model(self):
        verdict = evaluate_domain("gpu_admission", successful_evidence(STAGE_TYPES))
        self.assertTrue(verdict.accepted)
        self.assertEqual(tuple(x.stage for x in verdict.stages), STAGES)
        self.assertFalse(verdict.to_record()["native_inference_witnessed"])
        self.assertFalse(verdict.to_record()["physical_device_qualified"])
        self.assertFalse(verdict.to_record()["release_certified"])

    def test_each_independent_stage_failure_denies(self):
        for stage, evidence in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=stage):
                verdict = evaluate_domain("gpu_admission", evidence)
                self.assertFalse(verdict.accepted)
                self.assertIn(stage, [v.stage for v in verdict.stages if not v.accepted])

if __name__ == "__main__":
    unittest.main()
