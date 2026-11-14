"""Complete, original training source identity and independently checked labels."""
from __future__ import annotations
from dataclasses import replace
import unittest
from skeleton.ai.runtime.operational_ai.native_candidate.catalog import (
    DOMAINS, TOTAL_EXAMPLES, iter_examples, verify_exact, inventory,
)
from skeleton.ai.runtime.operational_ai.native_candidate.semantic_oracle import verify
from skeleton.ai.runtime.operational_ai.native_candidate.dedup import require_unique
from skeleton.ai.runtime.operational_ai.native_candidate.source_manifest import generate


class TestOriginalTrainingCatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = tuple(iter_examples())

    def test_complete_exact_source_tree(self):
        self.assertEqual(len(self.items), 576)
        self.assertEqual(len(DOMAINS), 24)
        self.assertTrue(verify_exact(self.items))
        self.assertEqual(inventory()["count"], TOTAL_EXAMPLES)

    def test_independent_authored_correctness(self):
        for row in self.items:
            with self.subTest(source=row.item_id):
                self.assertTrue(verify(row), row.item_id)

    def test_unique_prompts_and_sources(self):
        proof = require_unique(self.items)
        self.assertEqual(proof["unique_prompts"], TOTAL_EXAMPLES)
        self.assertEqual(proof["unique_sources"], TOTAL_EXAMPLES)

    def test_substituted_source_blocks_complete_corpus(self):
        changed = list(self.items)
        changed[0] = replace(changed[0], completion="wrong")
        self.assertFalse(verify_exact(tuple(changed)))

    def test_deleted_and_duplicated_source_blocks(self):
        self.assertFalse(verify_exact(self.items[:-1]))
        changed = list(self.items)
        changed[-1] = changed[0]
        self.assertFalse(verify_exact(tuple(changed)))

    def test_manifest_is_not_a_model_quality_receipt(self):
        proof=generate().record()
        self.assertEqual(proof["example_count"], 576)
        self.assertFalse(proof["model_trained"])
        self.assertFalse(proof["release_certified"])


if __name__ == "__main__":
    unittest.main()
