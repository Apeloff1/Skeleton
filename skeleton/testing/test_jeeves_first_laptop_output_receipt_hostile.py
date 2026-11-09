"""output_receipt hostile evidence and scope confusion regression."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.output_receipt.registry import STAGES, STAGE_TYPES, contracts

class HostileTests(unittest.TestCase):
    def test_all_eight_stages_are_mandatory(self):
        baseline = successful_evidence(STAGE_TYPES)
        for stage in STAGES:
            with self.subTest(stage=stage):
                partial = dict(baseline)
                partial.pop(stage)
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("output_receipt", partial)

    def test_unknown_stages_and_values_refused(self):
        baseline = successful_evidence(STAGE_TYPES)
        baseline["override"] = {"verified": True}
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("output_receipt", baseline)
        for candidate in (None, (), [], "", True, 1):
            with self.subTest(type=type(candidate).__name__), self.assertRaises(LaptopGateHold):
                evaluate_domain("output_receipt", candidate)

    def test_no_type_coercion_or_hidden_extra_stage_field(self):
        for stage, kind in STAGE_TYPES:
            with self.subTest(stage=stage):
                corrupt = successful_evidence(STAGE_TYPES)
                key = next(iter(corrupt[stage]))
                corrupt[stage][key] = [] if kind in ("sha_equal", "same_owner") else "1"
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("output_receipt", corrupt)
                corrupt = successful_evidence(STAGE_TYPES)
                corrupt[stage]["untrusted_extra"] = True
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("output_receipt", corrupt)

if __name__ == "__main__":
    unittest.main()
