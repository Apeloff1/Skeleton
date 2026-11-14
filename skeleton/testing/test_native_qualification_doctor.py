"""Read-only report doctor blocks counter spoofing, invented release and malformed JSON."""
from __future__ import annotations
import unittest

from skeleton.ai.runtime.operational_ai.native_qualification.canonical import encode
from skeleton.ai.runtime.operational_ai.native_qualification.diagnostics import inspect_report
from skeleton.ai.runtime.operational_ai.native_qualification.errors import QualificationError


def minimal_report():
    return {
        "schema":"skeleton.native-qualification.report.v1",
        "model":{"model_sha256":"a"*64},
        "metrics":{"cases_total":1,"cases_passed":1},
        "cases":[{"case_id":"case_1","passed":True}],
        "release_certified":False,"ci_qualified":False,
        "policy_threshold_met":False,
    }


class TestReadOnlyDoctor(unittest.TestCase):
    def test_canonical_report_shape(self):
        result=inspect_report(encode(minimal_report()))
        self.assertEqual(result["cases_total"],1)
        self.assertTrue(result["report_canonical"])
        self.assertFalse(result["release_certified"])

    def test_counter_conflict_fails(self):
        fake=minimal_report()
        fake["metrics"]["cases_passed"]=0
        with self.assertRaises(QualificationError):
            inspect_report(encode(fake))

    def test_release_claim_fails(self):
        fake=minimal_report()
        fake["release_certified"]=True
        with self.assertRaises(QualificationError):
            inspect_report(encode(fake))

    def test_duplicate_keys_fail(self):
        with self.assertRaises(QualificationError):
            inspect_report(b'{"schema":"skeleton.native-qualification.report.v1","schema":"fake"}')


if __name__ == "__main__":
    unittest.main()
