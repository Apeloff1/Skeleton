"""cold_restart: deterministic receipts do not grant native effect repetition."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import (
    successful_evidence, mutation_cases,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.cold_restart.registry import (
    STAGES, STAGE_TYPES, contracts,
)

from skeleton.jeeves.native_fabric.laptop_ops.predicates import required_keys
class TestReplay(unittest.TestCase):
    def test_reordered_stage_mapping_keeps_same_canonical_digest(self):
        e = successful_evidence(STAGE_TYPES)
        receipt = evaluate_domain("cold_restart", e).to_record()
        reordered = dict(reversed(tuple(e.items())))
        self.assertEqual(receipt, evaluate_domain("cold_restart", reordered).to_record())

    def test_each_negative_mutation_changes_proof_digest(self):
        initial = evaluate_domain("cold_restart", successful_evidence(STAGE_TYPES))
        for stage, sample in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=stage):
                result = evaluate_domain("cold_restart", sample)
                self.assertNotEqual(initial.evidence_sha256, result.evidence_sha256)
                self.assertFalse(result.accepted)

    def test_every_predicate_contract_declares_no_device_authority(self):
        docs = contracts()
        self.assertEqual(len(docs),8)
        for doc,(name,kind) in zip(docs,STAGE_TYPES):
            self.assertEqual(doc["stage"],name)
            self.assertEqual(doc["predicate"],kind)
            self.assertEqual(doc["required_fields"],list(required_keys(kind,name)))
            self.assertIs(doc["operator_proof_is_insufficient_for_activation"],True)
            self.assertIs(doc["device_qualified"],False)
