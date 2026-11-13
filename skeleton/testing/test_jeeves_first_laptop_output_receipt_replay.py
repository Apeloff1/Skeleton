"""output_receipt exact contract and immutable receipt replay regression."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.output_receipt.registry import STAGES, STAGE_TYPES, contracts

from skeleton.jeeves.native_fabric.laptop_ops.predicates import required_keys

class ReplayTests(unittest.TestCase):
    def test_independent_input_order_is_not_evidence(self):
        baseline = successful_evidence(STAGE_TYPES)
        first = evaluate_domain("output_receipt", baseline).to_record()
        backwards = dict(reversed(tuple(baseline.items())))
        self.assertEqual(first, evaluate_domain("output_receipt", backwards).to_record())
        self.assertEqual(first, evaluate_domain("output_receipt", baseline).to_record())

    def test_mutating_any_stage_changes_diagnostic_receipt(self):
        first = evaluate_domain("output_receipt", successful_evidence(STAGE_TYPES))
        for stage, changed in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=stage):
                next_result = evaluate_domain("output_receipt", changed)
                self.assertNotEqual(first.evidence_sha256, next_result.evidence_sha256)
                self.assertFalse(next_result.accepted)

    def test_typed_contracts_cannot_prove_hardware(self):
        self.assertEqual(len(contracts()), 8)
        for record, (stage, kind) in zip(contracts(), STAGE_TYPES):
            with self.subTest(stage=stage):
                self.assertEqual(record["domain"], "output_receipt")
                self.assertEqual(record["stage"], stage)
                self.assertEqual(record["predicate"], kind)
                self.assertEqual(record["required_fields"], list(required_keys(kind, stage)))
                self.assertIs(record["device_qualified"], False)
                self.assertIs(record["operator_proof_is_insufficient_for_activation"], True)

if __name__ == "__main__":
    unittest.main()
