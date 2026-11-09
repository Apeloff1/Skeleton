"""memory_consent: canonical source fingerprints and eight exact contracts."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import (
    successful_evidence, mutation_cases,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.memory_consent.registry import (
    STAGES, STAGE_TYPES, contracts,
)

from skeleton.jeeves.native_fabric.laptop_ops.predicates import required_keys

class TestReplay(unittest.TestCase):
    def test_canonical_digest_independent_of_mapping_insertion_order(self):
        source = successful_evidence(STAGE_TYPES)
        expected = evaluate_domain("memory_consent", source).to_record()
        alternative = dict(reversed(tuple(source.items())))
        self.assertEqual(expected, evaluate_domain("memory_consent", alternative).to_record())

    def test_every_negative_mutation_changes_the_receipt(self):
        good = evaluate_domain("memory_consent", successful_evidence(STAGE_TYPES))
        for stage, case in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=stage):
                bad = evaluate_domain("memory_consent", case)
                self.assertFalse(bad.accepted)
                self.assertNotEqual(good.evidence_sha256, bad.evidence_sha256)

    def test_every_contract_declares_inert_device_status(self):
        for doc,(stage,kind) in zip(contracts(),STAGE_TYPES):
            with self.subTest(stage=stage):
                self.assertEqual(doc["domain"], "memory_consent")
                self.assertEqual(doc["stage"], stage)
                self.assertEqual(doc["predicate"], kind)
                self.assertEqual(doc["required_fields"], list(required_keys(kind,stage)))
                self.assertIs(doc["operator_proof_is_insufficient_for_activation"], True)
                self.assertIs(doc["device_qualified"], False)
