"""Original formatting training records and independent correct-answer oracle."""
from __future__ import annotations
from dataclasses import replace
import unittest

from skeleton.ai.runtime.operational_ai.native_candidate.catalog import iter_examples
from skeleton.ai.runtime.operational_ai.native_candidate.semantic_oracle import (
    expected_answer, verify,
)
from skeleton.ai.runtime.operational_ai.native_candidate.records import TrainingExample
from skeleton.ai.runtime.operational_ai.native_candidate.dedup import text_digest


class TestFormattingOriginalTraining(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = tuple(x for x in iter_examples() if x.domain == "formatting")

    def test_exact_24_source_records(self):
        self.assertEqual(len(self.records), 24)
        self.assertEqual(len({x.item_id for x in self.records}), 24)

    def test_correct_answer_recomputed_independently(self):
        for item in self.records:
            with self.subTest(item=item.item_id):
                self.assertTrue(verify(item), item.item_id)
                self.assertEqual(expected_answer(item), item.completion)

    def test_all_sources_have_original_rights_and_unique_groups(self):
        self.assertEqual(len({x.group_id for x in self.records}), 24)
        for item in self.records:
            with self.subTest(item=item.item_id):
                self.assertEqual(item.license_id, "skeleton_original")
                self.assertEqual(item.rights_status, "allowed")
                self.assertEqual(item.training_scope, "offline_native_candidate_training")
                self.assertEqual(item.group_id, item.item_id)

    def test_roundtrip_cannot_change_identity(self):
        import json
        for item in self.records:
            with self.subTest(item=item.item_id):
                reread = TrainingExample.parse(json.dumps(item.record()).encode("utf-8"))
                self.assertEqual(reread, item)
                self.assertEqual(reread.source_digest, item.source_digest)

    def test_model_answer_cannot_redefine_source_truth(self):
        item = self.records[-1]
        mutated = replace(item, completion=item.completion + "_tampered")
        self.assertNotEqual(mutated.source_digest, item.source_digest)
        self.assertFalse(verify(mutated))

    def test_finite_training_render(self):
        self.assertEqual(len({text_digest(item.prompt) for item in self.records}), 24)
        for item in self.records:
            with self.subTest(item=item.item_id):
                self.assertLessEqual(len(item.render().encode("utf-8")), 4096)
                self.assertIn("Response:", item.render())
                self.assertNotIn("\x00", item.render())


if __name__ == "__main__":
    unittest.main()
