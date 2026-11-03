"""Original unit_words training records and independent correct-answer oracle."""
from __future__ import annotations
from dataclasses import replace
import unittest

from skeleton.ai.runtime.operational_ai.native_candidate.catalog import iter_examples
from skeleton.ai.runtime.operational_ai.native_candidate.semantic_oracle import (
    expected_answer, verify,
)
from skeleton.ai.runtime.operational_ai.native_candidate.records import TrainingExample
from skeleton.ai.runtime.operational_ai.native_candidate.dedup import text_digest
from skeleton.ai.runtime.operational_ai.native_candidate.splits import partition


class TestUnitWordsOriginalTraining(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = tuple(x for x in iter_examples() if x.domain == "unit_words")

    def test_domain_has_exactly_24_real_training_records(self):
        self.assertEqual(len(self.records), 24)
        self.assertEqual(len({x.item_id for x in self.records}), 24)

    def test_every_answer_is_independently_derived(self):
        for item in self.records:
            with self.subTest(item=item.item_id):
                self.assertTrue(verify(item), item.item_id)
                self.assertEqual(expected_answer(item), item.completion)

    def test_source_roundtrip_and_rights(self):
        for item in self.records:
            with self.subTest(item=item.item_id):
                self.assertEqual(TrainingExample.parse(
                    __import__("json").dumps(item.record()).encode("utf-8")), item)
                self.assertEqual(item.license_id, "skeleton_original")
                self.assertEqual(item.training_scope, "offline_native_candidate_training")
                self.assertEqual(item.rights_status, "allowed")

    def test_distinct_canonical_prompts_and_groups(self):
        self.assertEqual(len({text_digest(item.prompt) for item in self.records}), 24)
        self.assertEqual(len({item.group_id for item in self.records}), 24)
        self.assertTrue(all(item.group_id == item.item_id for item in self.records))

    def test_tampered_answer_detected(self):
        item = self.records[0]
        changed = replace(item, completion=item.completion + " incorrect")
        self.assertFalse(verify(changed))
        self.assertNotEqual(item.source_digest, changed.source_digest)

    def test_every_training_line_is_bounded_and_nonempty(self):
        for item in self.records:
            with self.subTest(item=item.item_id):
                line = item.render()
                self.assertLessEqual(len(line.encode("utf-8")), 4096)
                self.assertIn("Instruction:", line)
                self.assertIn("Response:", line)
                self.assertNotIn("\x00", line)


if __name__ == "__main__":
    unittest.main()
