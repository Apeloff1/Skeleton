"""Private prompts, bearer strings and raw model text stay out of public reports."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.native_qualification.privacy import inspect_public_fields
from skeleton.ai.runtime.operational_ai.native_qualification.errors import QualificationError


class TestQualificationPrivacy(unittest.TestCase):
    def test_public_metrics_only(self):
        value={"model":{"model_sha256":"a"*64},"metrics":{"cases_total":480},
               "cases":[{"case_id":"qa_1","output_sha256":"b"*64}]}
        self.assertTrue(inspect_public_fields(value)["publishable"])

    def test_block_raw_generated_text(self):
        for key in ("prompt","raw_output","model_output","secret","bearer"):
            with self.subTest(key=key):
                report={"cases":[{"case_id":"a",key:"secret value"}]}
                proof=inspect_public_fields(report)
                self.assertFalse(proof["publishable"])
                self.assertTrue(proof["blocked_fields"])

    def test_invalid_tree_types_refused(self):
        with self.assertRaises(QualificationError):
            inspect_public_fields({"danger":object()})

    def test_empty_prompt_field_is_never_publishable(self):
        # Even empty raw-prompt fields are forbidden in public evidence.
        report = {"cases": [{"case_id": "synthetic", "prompt": ""}]}
        proof = inspect_public_fields(report)
        self.assertFalse(proof["publishable"])
        self.assertEqual(proof["blocked_fields"], ("report.cases[0].prompt",))


if __name__ == "__main__":
    unittest.main()
