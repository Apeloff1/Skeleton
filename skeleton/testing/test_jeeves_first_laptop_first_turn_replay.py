"""first_turn: deterministic source fingerprints and non-authority contracts."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import (
    successful_evidence, mutation_cases,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.first_turn.registry import (
    STAGES, STAGE_TYPES, contracts,
)

from skeleton.jeeves.native_fabric.laptop_ops.predicates import required_keys
class TestReplay(unittest.TestCase):
    def test_source_order_does_not_affect_canonical_receipt(self):
        original = successful_evidence(STAGE_TYPES)
        expected = evaluate_domain("first_turn", original).to_record()
        reordered = dict(reversed(tuple(original.items())))
        self.assertEqual(expected, evaluate_domain("first_turn", reordered).to_record())

    def test_mutating_eight_independent_stages_changes_fingerprint(self):
        initial = evaluate_domain("first_turn", successful_evidence(STAGE_TYPES))
        for stage, sample in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=stage):
                bad = evaluate_domain("first_turn", sample)
                self.assertNotEqual(bad.evidence_sha256, initial.evidence_sha256)
                self.assertFalse(bad.accepted)

    def test_contracts_do_not_certify_hardware_or_release(self):
        for desc,(label,kind) in zip(contracts(),STAGE_TYPES):
            self.assertEqual(desc["domain"], "first_turn")
            self.assertEqual(desc["stage"], label)
            self.assertEqual(desc["predicate"], kind)
            self.assertEqual(desc["required_fields"], list(required_keys(kind,label)))
            self.assertIs(desc["device_qualified"], False)
            self.assertIs(desc["operator_proof_is_insufficient_for_activation"], True)
