"""Latency and error measurements are source-derived, finite and reproducible."""
from __future__ import annotations
import unittest

from skeleton.ai.runtime.operational_ai.native_qualification.metrics import (
    percentile_int,
)
from skeleton.ai.runtime.operational_ai.native_qualification.latency import summarize
from skeleton.ai.runtime.operational_ai.native_qualification.failure_taxonomy import classify
from skeleton.ai.runtime.operational_ai.native_qualification.sampling import choose_subset
from skeleton.ai.runtime.operational_ai.native_qualification.corpus import iter_cases
from skeleton.ai.runtime.operational_ai.native_qualification.errors import QualificationError


class TestQualificationMetrics(unittest.TestCase):
    def test_empty_percentiles_never_invent_numbers(self):
        self.assertIsNone(percentile_int([],50))
        self.assertIsNone(percentile_int([],95))

    def test_nearest_rank(self):
        self.assertEqual(percentile_int([100,20,40,60,80],50),60)
        self.assertEqual(percentile_int([100,20,40,60,80],95),100)

    def test_measured_token_throughput(self):
        value=summarize([1000,500],[5,10])
        self.assertEqual(value.requests,2)
        self.assertEqual(value.generated_tokens,15)
        self.assertEqual(value.p95_ms,1000)
        self.assertEqual(value.tokens_per_sec,10)

    def test_zero_time_not_divided(self):
        self.assertEqual(summarize([0],[0]).tokens_per_sec,0.0)

    def test_malformed_numbers_rejected(self):
        with self.assertRaises(QualificationError):
            summarize([-1],[5])
        with self.assertRaises(QualificationError):
            percentile_int([True],50)

    def test_failure_categories(self):
        self.assertEqual(classify(None,checks_passed=False),"model-quality")
        self.assertEqual(classify("native-call-failed",checks_passed=False),"native-runtime")
        self.assertEqual(classify("native-revision",checks_passed=False),"durable-recovery")

    def test_reproducible_dev_subset_is_not_full(self):
        cases=tuple(iter_cases())
        a=choose_subset(cases,max_cases=12,seed=123)
        b=choose_subset(cases,max_cases=12,seed=123)
        self.assertEqual(a,b)
        self.assertEqual(len(a),12)
        self.assertEqual(len({c.case_id for c in a}),12)


if __name__ == "__main__":
    unittest.main()
