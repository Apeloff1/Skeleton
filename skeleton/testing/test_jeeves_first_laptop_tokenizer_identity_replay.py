"""Tokenizer source evidence receipt determinism and policy schema."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.tokenizer_identity.registry import STAGES, STAGE_TYPES, contracts

from skeleton.jeeves.native_fabric.laptop_ops.predicates import required_keys

class TokenizerReplay(unittest.TestCase):
    def test_input_insertion_order_is_not_an_authority(self):
        source = successful_evidence(STAGE_TYPES)
        expected = evaluate_domain("tokenizer_identity", source).to_record()
        self.assertEqual(expected, evaluate_domain("tokenizer_identity", dict(reversed(tuple(source.items())))).to_record())

    def test_every_negative_case_changes_digest(self):
        original = evaluate_domain("tokenizer_identity", successful_evidence(STAGE_TYPES))
        for label, modified in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=label):
                changed = evaluate_domain("tokenizer_identity", modified)
                self.assertNotEqual(original.evidence_sha256, changed.evidence_sha256)

    def test_stage_contracts_are_not_device_proof(self):
        self.assertEqual(len(contracts()), 8)
        for record, (stage, kind) in zip(contracts(), STAGE_TYPES):
            self.assertEqual(record["stage"], stage)
            self.assertEqual(record["predicate"], kind)
            self.assertEqual(record["required_fields"], list(required_keys(kind, stage)))
            self.assertIs(record["device_qualified"], False)
