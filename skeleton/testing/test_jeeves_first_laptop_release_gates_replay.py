"""Release-source evidence ordering cannot create an independent CI pass."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import (
    successful_evidence, mutation_cases,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.release_gates.registry import (
    STAGES, STAGE_TYPES, contracts,
)

from skeleton.jeeves.native_fabric.laptop_ops.predicates import required_keys

class TestReleaseReplay(unittest.TestCase):
    def test_input_mapping_order_does_not_change_receipt(self):
        initial = successful_evidence(STAGE_TYPES)
        expected = evaluate_domain("release_gates", initial).to_record()
        alternative = dict(reversed(tuple(initial.items())))
        self.assertEqual(expected, evaluate_domain("release_gates", alternative).to_record())

    def test_negative_stage_changes_source_fingerprint(self):
        base = evaluate_domain("release_gates", successful_evidence(STAGE_TYPES))
        for stage,case in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=stage):
                changed = evaluate_domain("release_gates",case)
                self.assertNotEqual(base.evidence_sha256,changed.evidence_sha256)
                self.assertFalse(changed.accepted)

    def test_all_source_stage_contracts_explicitly_not_attested(self):
        self.assertEqual(len(contracts()),8)
        for doc,(stage,kind) in zip(contracts(),STAGE_TYPES):
            self.assertEqual(doc["stage"],stage)
            self.assertEqual(doc["predicate"],kind)
            self.assertEqual(doc["required_fields"],list(required_keys(kind,stage)))
            self.assertIs(doc["device_qualified"],False)
            self.assertIs(doc["operator_proof_is_insufficient_for_activation"],True)
