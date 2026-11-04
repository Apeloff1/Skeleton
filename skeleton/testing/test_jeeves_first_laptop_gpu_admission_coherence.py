"""gpu_admission rejects cross-stage inconsistency despite local predicate success."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.gpu_admission.registry import STAGES, STAGE_TYPES, contracts

class CoherenceTests(unittest.TestCase):
    def test_consistent_case_is_source_only(self):
        verdict = evaluate_domain("gpu_admission", successful_evidence(STAGE_TYPES))
        self.assertTrue(verdict.accepted)
        self.assertFalse(verdict.to_record()["release_certified"])

    def test_individually_allowed_values_can_still_conflict(self):
        evidence = successful_evidence(STAGE_TYPES)
        evidence["offload_layers"].update({"used": 513, "limit": 1024})
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("gpu_admission", evidence)

    def test_missing_canonical_stage_cannot_be_replaced(self):
        evidence = successful_evidence(STAGE_TYPES)
        del evidence[STAGES[0]]
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("gpu_admission", evidence)

if __name__ == "__main__":
    unittest.main()
