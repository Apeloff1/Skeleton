"""Adversarial model_manifest whole-domain admission checks."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.model_manifest.registry import STAGES, STAGE_TYPES, contracts

class TestModelManifestAdmission(unittest.TestCase):
    def test_eight_obligations_and_only_source_claims(self):
        accepted = evaluate_domain("model_manifest", successful_evidence(STAGE_TYPES))
        self.assertTrue(accepted.accepted)
        self.assertEqual([x.stage for x in accepted.stages], list(STAGES))
        self.assertEqual(len(contracts()), 8)
        self.assertFalse(accepted.to_record()["native_inference_witnessed"])
        self.assertFalse(accepted.to_record()["release_certified"])

    def test_no_omitted_failure_is_silently_passed(self):
        for label, mutation in mutation_cases(STAGE_TYPES):
            with self.subTest(safeguard=label):
                verdict = evaluate_domain("model_manifest", mutation)
                self.assertFalse(verdict.accepted)
                self.assertEqual([v.stage for v in verdict.stages if not v.accepted], [label])

if __name__ == "__main__":
    unittest.main()
