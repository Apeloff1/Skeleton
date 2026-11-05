"""Stage metadata cannot confer model or license authority."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.predicates import required_keys
from skeleton.jeeves.native_fabric.laptop_ops.domains.model_manifest.registry import contracts, STAGE_TYPES
class TestModelManifestContract(unittest.TestCase):
    def test_exact_declared_types_and_fields(self):
        docs = contracts()
        self.assertEqual(len(docs), 8)
        for item, (name, kind) in zip(docs, STAGE_TYPES):
            with self.subTest(name=name):
                self.assertEqual(item["stage"], name)
                self.assertEqual(item["predicate"], kind)
                self.assertEqual(item["required_fields"], list(required_keys(kind, name)))
                self.assertIs(item["operator_proof_is_insufficient_for_activation"], True)
                self.assertIs(item["device_qualified"], False)

    def test_no_duplicate_stage_identifiers(self):
        self.assertEqual(len({x[0] for x in STAGE_TYPES}), 8)

if __name__ == "__main__":
    unittest.main()
