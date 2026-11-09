"""Context window evidence receipts remain deterministic and non-authoritative."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.context_window.registry import STAGES, STAGE_TYPES, contracts

from skeleton.jeeves.native_fabric.laptop_ops.predicates import required_keys

class TestContextReplay(unittest.TestCase):
    def test_input_order_and_repeat_are_not_authority(self):
        evidence = successful_evidence(STAGE_TYPES)
        report = evaluate_domain("context_window", evidence).to_record()
        reversed_order = dict(reversed(tuple(evidence.items())))
        self.assertEqual(report, evaluate_domain("context_window", reversed_order).to_record())

    def test_stage_contracts_are_complete_and_typed(self):
        self.assertEqual(len(contracts()), 8)
        for doc, (stage, predicate) in zip(contracts(), STAGE_TYPES):
            self.assertEqual(doc["domain"], "context_window")
            self.assertEqual(doc["stage"], stage)
            self.assertEqual(doc["predicate"], predicate)
            self.assertEqual(doc["required_fields"], list(required_keys(predicate, stage)))
            self.assertIs(doc["device_qualified"], False)
            self.assertIs(doc["operator_proof_is_insufficient_for_activation"], True)

    def test_one_stage_denial_changes_receipt_hash(self):
        source = successful_evidence(STAGE_TYPES)
        baseline = evaluate_domain("context_window", source).evidence_sha256
        for stage, doc in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=stage):
                self.assertNotEqual(baseline, evaluate_domain("context_window", doc).evidence_sha256)
