"""output_receipt rejects cross-stage inconsistency despite local predicate success."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.output_receipt.registry import STAGES, STAGE_TYPES, contracts

class CoherenceTests(unittest.TestCase):
    def test_consistent_case_is_source_only(self):
        verdict = evaluate_domain("output_receipt", successful_evidence(STAGE_TYPES))
        self.assertTrue(verdict.accepted)
        self.assertFalse(verdict.to_record()["release_certified"])

    def test_individually_allowed_values_can_still_conflict(self):
        evidence = successful_evidence(STAGE_TYPES)
        evidence["replayed_digest"] = {"expected_sha256": "b" * 64, "observed_sha256": "b" * 64}
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("output_receipt", evidence)

    def test_missing_canonical_stage_cannot_be_replaced(self):
        evidence = successful_evidence(STAGE_TYPES)
        del evidence[STAGES[0]]
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("output_receipt", evidence)

if __name__ == "__main__":
    unittest.main()
