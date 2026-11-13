"""signed_sources: deterministic canonical receipts and machine-readable contracts."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.signed_sources.registry import STAGES, STAGE_TYPES, contracts

from skeleton.jeeves.native_fabric.laptop_ops.predicates import required_keys
class TestReplay(unittest.TestCase):
    def test_stage_order_is_registry_defined(self):
        source = successful_evidence(STAGE_TYPES)
        initial = evaluate_domain("signed_sources", source).to_record()
        backwards = dict(reversed(tuple(source.items())))
        self.assertEqual(initial, evaluate_domain("signed_sources", backwards).to_record())

    def test_mutations_change_receipt_fingerprints(self):
        baseline = evaluate_domain("signed_sources", successful_evidence(STAGE_TYPES))
        for stage, case in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=stage):
                modified = evaluate_domain("signed_sources", case)
                self.assertNotEqual(baseline.evidence_sha256, modified.evidence_sha256)
                self.assertFalse(modified.accepted)

    def test_eight_typed_contracts_cannot_grant_rights(self):
        self.assertEqual(len(contracts()), 8)
        for desc, (stage, kind) in zip(contracts(), STAGE_TYPES):
            self.assertEqual(desc["stage"], stage)
            self.assertEqual(desc["predicate"], kind)
            self.assertEqual(desc["required_fields"], list(required_keys(kind, stage)))
            self.assertIs(desc["operator_proof_is_insufficient_for_activation"], True)
            self.assertIs(desc["device_qualified"], False)
