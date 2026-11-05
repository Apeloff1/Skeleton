"""Full original domain inventory and source integrity: grounding.

This is static qualification-infrastructure coverage, NOT a simulated
model-quality pass. The actual pinned native runtime must execute all cases.
"""
from __future__ import annotations
import unittest

from skeleton.ai.runtime.operational_ai.native_qualification.cases import (
    QualificationCase,
)
from skeleton.ai.runtime.operational_ai.native_qualification.corpus import (
    iter_cases,
)
from skeleton.ai.runtime.operational_ai.native_qualification.canonical import (
    encode, decode,
)
from skeleton.ai.runtime.operational_ai.native_qualification.checks import Check
from skeleton.ai.runtime.operational_ai.native_qualification.errors import QualificationError


class TestGroundingQualification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = tuple(x for x in iter_cases() if x.domain == "grounding")

    def test_exact_24_authored_cases(self):
        self.assertEqual(len(self.records), 24)

    def test_unique_task_inputs(self):
        self.assertEqual(
            len({tuple(step.prompt for step in case.steps) for case in self.records}),
            24,
        )

    def test_case_ids_and_digests_are_canonical(self):
        self.assertEqual(len({c.case_id for c in self.records}), 24)
        for case in self.records:
            with self.subTest(case=case.case_id):
                self.assertTrue(case.case_id.startswith("grounding_"))
                self.assertEqual(len(case.content_sha256), 64)
                self.assertEqual(QualificationCase.from_json(decode(encode(case.record()))), case)
                self.assertTrue(case.license_id == "original_fixture")

    def test_all_terminal_steps_have_quality_oracles(self):
        for case in self.records:
            with self.subTest(case=case.case_id):
                self.assertTrue(case.steps)
                self.assertLessEqual(len(case.steps), 4)
                for step in case.steps:
                    self.assertTrue(step.prompt)
                    self.assertTrue(step.checks or step.intermediate)
                    for check in step.checks:
                        self.assertIsInstance(check, Check)

    def test_no_model_result_is_claimed_by_fixture(self):
        for case in self.records:
            with self.subTest(case=case.case_id):
                self.assertFalse(hasattr(case, "passed"))
                self.assertFalse(hasattr(case, "model_output"))
                self.assertFalse(hasattr(case, "release_certified"))

    def test_modifying_case_changes_source_digest(self):
        record = self.records[0].record()
        record["objective"] += " changed"
        changed = QualificationCase.from_json(record)
        self.assertNotEqual(changed.content_sha256, self.records[0].content_sha256)

    def test_empty_prompt_denied(self):
        damaged = self.records[0].record()
        damaged["steps"][0]["prompt"] = ""
        with self.assertRaises(QualificationError):
            QualificationCase.from_json(damaged)


if __name__ == "__main__":
    unittest.main()
