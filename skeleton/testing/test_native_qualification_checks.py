"""Actual deterministic output checks are independent of model-supplied claims."""
from __future__ import annotations
import unittest

from skeleton.ai.runtime.operational_ai.native_qualification.checks import (
    Check, evaluate,
)
from skeleton.ai.runtime.operational_ai.native_qualification.errors import QualificationError


class TestNativeChecks(unittest.TestCase):
    def test_exact_false_and_true(self):
        check = Check("exact", "5")
        self.assertTrue(evaluate(check, "  5\n").passed)
        self.assertFalse(evaluate(check, "The answer is 5").passed)

    def test_casefold_exact(self):
        self.assertTrue(evaluate(Check("casefold_exact","TRUE"),"true").passed)

    def test_structured_json_exact_types(self):
        check = Check("json_equals", {"n": 2, "active": True})
        self.assertTrue(evaluate(check,'{"active":true,"n":2}').passed)
        self.assertFalse(evaluate(check,'{"active":"true","n":"2"}').passed)

    def test_json_duplicate_key_is_failure(self):
        got = evaluate(Check("json_equals", {"a":1}), '{"a":1,"a":1}')
        self.assertFalse(got.passed)
        self.assertEqual(got.diagnostic, "invalid-json-output")

    def test_negative_evidence_assertion(self):
        self.assertTrue(evaluate(Check("not_contains","SECRET"),"SAFE").passed)
        self.assertFalse(evaluate(Check("not_contains","SECRET"),"SECRET").passed)

    def test_source_label_has_brackets(self):
        self.assertTrue(evaluate(Check("citation_label","source_7"),"Fact [source_7]").passed)
        self.assertFalse(evaluate(Check("citation_label","source_7"),"Fact source_7").passed)

    def test_exact_number_enforces_numeric(self):
        self.assertTrue(evaluate(Check("numeric_exact",12),"12").passed)
        self.assertFalse(evaluate(Check("numeric_exact",12),"twelve").passed)

    def test_regex_fullmatch_not_substring(self):
        check = Check("regex_full", r"[A-Z]{2}")
        self.assertTrue(evaluate(check,"AB").passed)
        self.assertFalse(evaluate(check,"XABY").passed)

    def test_word_budget(self):
        self.assertTrue(evaluate(Check("max_words",2),"one two").passed)
        self.assertFalse(evaluate(Check("max_words",2),"one two three").passed)

    def test_check_unknown_field_denied(self):
        with self.assertRaises(QualificationError):
            Check.from_json({"kind":"exact","expected":"a","shell":True})


if __name__ == "__main__":
    unittest.main()
