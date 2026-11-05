"""CPU admission receipts and contracts remain deterministic."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import (
    successful_evidence, mutation_cases,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.cpu_admission.registry import (
    STAGES, STAGE_TYPES, contracts,
)

from skeleton.jeeves.native_fabric.laptop_ops.predicates import required_keys

class TestCpuReplay(unittest.TestCase):
    def test_mapping_insertion_order_is_not_part_of_receipt_identity(self):
        source = successful_evidence(STAGE_TYPES)
        expected = evaluate_domain("cpu_admission", source).to_record()
        reversed_source = dict(reversed(tuple(source.items())))
        self.assertEqual(expected, evaluate_domain("cpu_admission", reversed_source).to_record())

    def test_each_denied_stage_changes_receipt_digest(self):
        baseline = evaluate_domain("cpu_admission", successful_evidence(STAGE_TYPES))
        for stage, sample in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=stage):
                changed = evaluate_domain("cpu_admission", sample)
                self.assertNotEqual(baseline.evidence_sha256, changed.evidence_sha256)
                self.assertFalse(changed.accepted)

    def test_stage_contracts_require_exact_strict_fields(self):
        descriptions = contracts()
        self.assertEqual(len(descriptions), 8)
        self.assertEqual(tuple(item["stage"] for item in descriptions), STAGES)
        for doc,(stage,kind) in zip(descriptions,STAGE_TYPES):
            with self.subTest(stage=stage):
                self.assertEqual(doc["domain"], "cpu_admission")
                self.assertEqual(doc["predicate"], kind)
                self.assertEqual(doc["required_fields"], list(required_keys(kind,stage)))
                self.assertIs(doc["operator_proof_is_insufficient_for_activation"], True)
                self.assertIs(doc["device_qualified"], False)
