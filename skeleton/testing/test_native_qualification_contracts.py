"""Canonical native evaluation inputs: reject ambiguity and invented authority."""
from __future__ import annotations
import unittest

from skeleton.ai.runtime.operational_ai.native_qualification.canonical import (
    decode, encode, identity, integer, sha256,
)
from skeleton.ai.runtime.operational_ai.native_qualification.cases import QualificationCase, Step
from skeleton.ai.runtime.operational_ai.native_qualification.checks import Check
from skeleton.ai.runtime.operational_ai.native_qualification.errors import QualificationError


class TestQualificationContracts(unittest.TestCase):
    def test_duplicate_keys_denied(self):
        with self.assertRaises(QualificationError):
            decode(b'{"a":1,"a":2}')

    def test_nan_and_infinity_denied(self):
        for value in (b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}'):
            with self.subTest(value=value), self.assertRaises(QualificationError):
                decode(value)

    def test_canonical_order_is_stable(self):
        left = encode({"a": 1, "b": 2})
        right = encode({"b": 2, "a": 1})
        self.assertEqual(left, right)
        self.assertEqual(sha256(left), sha256(right))

    def test_boolean_not_integer(self):
        with self.assertRaises(QualificationError):
            integer(True, "quota", 0, 10)

    def test_invalid_identity(self):
        for name in ("", "../secret", "NATIVE", "x"*65):
            with self.assertRaises(QualificationError):
                identity(name)

    def test_invalid_check_kind(self):
        with self.assertRaises(QualificationError):
            Check("untrusted_script", "pass")

    def test_case_roundtrip_is_lossless(self):
        case = QualificationCase(
            "qa_01", "arithmetic", "high", "Compute exactly",
            (Step("What is 1+1?", (Check("exact", "2"),)),),
        )
        self.assertEqual(QualificationCase.from_json(decode(encode(case.record()))), case)
        self.assertEqual(len(case.content_sha256), 64)

    def test_empty_unchecked_terminal_refused(self):
        with self.assertRaises(QualificationError):
            Step("hello", ())

    def test_unbounded_case_steps_refused(self):
        step = Step("hi", (Check("exact", "hello"),))
        with self.assertRaises(QualificationError):
            QualificationCase("qa_01","logic","high","logic test",(step,)*5)

    def test_case_unknown_field_refused(self):
        case = QualificationCase(
            "qa_01", "logic", "high", "logic test",
            (Step("hi", (Check("exact","hi"),)),)
        ).record()
        case["model_report_passed"] = True
        with self.assertRaises(QualificationError):
            QualificationCase.from_json(case)


if __name__ == "__main__":
    unittest.main()
