"""Source-only bootstrap admission regression; not hardware qualification."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import (
    successful_evidence, mutation_cases,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.bootstrap.registry import (
    STAGES, STAGE_TYPES, evaluate, contracts,
)


class TestBootstrapAdmission(unittest.TestCase):

    def test_every_safeguard_is_required(self):
        fixture = successful_evidence(STAGE_TYPES)
        result = evaluate_domain("bootstrap", fixture)
        self.assertTrue(result.accepted)
        self.assertEqual(len(result.stages), 8)
        self.assertEqual(len(contracts()), 8)
        self.assertFalse(result.to_record()["native_inference_witnessed"])
        self.assertFalse(result.to_record()["release_certified"])

    def test_each_failed_predicate_holds_whole_domain(self):
        for changed, sample in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=changed):
                verdict = evaluate_domain("bootstrap", sample)
                self.assertFalse(verdict.accepted)
                self.assertIn(changed, [v.stage for v in verdict.stages
                                       if not v.accepted])
                self.assertFalse(verdict.to_record()["physical_device_qualified"])

    def test_domain_stage_order_is_deterministic(self):
        fixture = successful_evidence(STAGE_TYPES)
        shuffled = dict(reversed(list(fixture.items())))
        self.assertEqual(
            evaluate_domain("bootstrap", fixture).to_record(),
            evaluate_domain("bootstrap", shuffled).to_record(),
        )

if __name__ == "__main__":
    unittest.main()
