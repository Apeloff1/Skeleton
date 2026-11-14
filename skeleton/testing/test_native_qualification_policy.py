"""Threshold and incomplete-evidence policy cannot self-certify a release."""
from __future__ import annotations
import unittest

from skeleton.ai.runtime.operational_ai.native_qualification.policy import Threshold
from skeleton.ai.runtime.operational_ai.native_qualification.quality_hold import (
    REQUIRED, Hold, assess,
)
from skeleton.ai.runtime.operational_ai.native_qualification.errors import QualificationError


class TestQualificationPolicy(unittest.TestCase):
    def test_high_threshold_requires_evidence(self):
        policy = Threshold()
        self.assertFalse(policy.decide(
            total=100, passed=100, failed_calls=0,
            critical_failed=0, domains={"test":(100,100)},
            evidence_complete=False,
        ))

    def test_critical_failure_holds(self):
        self.assertFalse(Threshold().decide(
            total=100, passed=99, failed_calls=0, critical_failed=1,
            domains={"test":(99,100)}, evidence_complete=True,
        ))

    def test_no_silent_domain_regression(self):
        self.assertFalse(Threshold(minimum_domain_percent=90).decide(
            total=100, passed=96, failed_calls=0, critical_failed=0,
            domains={"good":(88,90),"bad":(8,10)}, evidence_complete=True,
        ))

    def test_empty_holds_cannot_release(self):
        state = assess(())
        self.assertFalse(state["release_qualified"])
        self.assertEqual(len(state["missing"]),len(REQUIRED))

    def test_true_hold_requires_digest_proof(self):
        with self.assertRaises(QualificationError):
            Hold("native_model", True)

    def test_all_fields_do_not_mean_ci_is_real(self):
        holds = tuple(Hold(name, False) for name in REQUIRED)
        state = assess(holds)
        self.assertFalse(state["release_qualified"])
        self.assertEqual(len(state["pending"]),len(REQUIRED))


if __name__ == "__main__":
    unittest.main()
