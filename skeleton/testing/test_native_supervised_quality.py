"""Independent validation loss selection cannot self-certify production weights."""
from __future__ import annotations
from dataclasses import replace
import unittest
from skeleton.ai.runtime.operational_ai.native_supervised.loss import MeasuredLoss
from skeleton.ai.runtime.operational_ai.native_supervised.policy import SupervisedPolicy
from skeleton.ai.runtime.operational_ai.native_supervised.quality_threshold import judge
from skeleton.ai.runtime.operational_ai.native_supervised.errors import SupervisedRejected


def loss(value:int)->MeasuredLoss:
    return MeasuredLoss(100,value/10000,value/1000000,value,2.0,"a"*64)


class TestQualitySelection(unittest.TestCase):
    def test_real_improvement_required(self):
        policy=SupervisedPolicy(operator_approved=True)
        report=judge(loss(2000000),loss(1500000),policy)
        self.assertEqual(report.delta_ppm,500000)
        self.assertTrue(report.eligible_for_independent_probes)
        self.assertFalse(report.report()["production_authorized"])

    def test_regression_is_not_improvement(self):
        report=judge(loss(1500000),loss(2000000),
                     SupervisedPolicy(operator_approved=True))
        self.assertFalse(report.improved)
        self.assertFalse(report.eligible_for_independent_probes)

    def test_no_invariant_loss_claims_improvement(self):
        report=judge(loss(1000000),loss(1000000),
                     SupervisedPolicy(operator_approved=True))
        self.assertFalse(report.eligible_for_independent_probes)

    def test_source_drift_refused(self):
        other=replace(loss(1000000),windows_sha256="b"*64)
        with self.assertRaises(SupervisedRejected):
            judge(loss(2000000),other,
                  SupervisedPolicy(operator_approved=True))

    def test_strict_threshold_refuses_small_delta(self):
        policy=SupervisedPolicy(operator_approved=True,min_improvement_ppm=500000)
        report=judge(loss(2000000),loss(1800000),policy)
        self.assertFalse(report.eligible_for_independent_probes)


if __name__=="__main__":
    unittest.main()
