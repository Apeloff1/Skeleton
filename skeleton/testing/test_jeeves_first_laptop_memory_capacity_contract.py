"""Memory stage contracts do not certify device or model resources."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.memory_capacity.registry import STAGES, STAGE_TYPES, contracts

from skeleton.jeeves.native_fabric.laptop_ops.predicates import required_keys

class TestMemoryContracts(unittest.TestCase):
    def test_eight_typed_bounded_contracts(self):
        docs = contracts()
        self.assertEqual(len(docs), 8)
        for doc, (label, kind) in zip(docs, STAGE_TYPES):
            with self.subTest(label=label):
                self.assertEqual(doc["domain"], "memory_capacity")
                self.assertEqual(doc["stage"], label)
                self.assertEqual(doc["predicate"], kind)
                self.assertEqual(doc["required_fields"], list(required_keys(kind, label)))
                self.assertIs(doc["device_qualified"], False)
                self.assertIs(doc["operator_proof_is_insufficient_for_activation"], True)
