"""Nearest-rank latency uses observed integer samples and no fake timing."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.native_supervised.latency_stats import nearest_rank
from skeleton.ai.runtime.operational_ai.native_supervised.errors import SupervisedRejected


class TestNativeLatencyStats(unittest.TestCase):
    def test_nearest_rank_integer_ordering(self):
        sample=[100,20,40,60,80]
        self.assertEqual(nearest_rank(sample,50),60)
        self.assertEqual(nearest_rank(sample,95),100)
        self.assertEqual(nearest_rank(sample,99),100)

    def test_single_sample_has_same_percentile(self):
        for p in (1,50,95,99,100):
            self.assertEqual(nearest_rank([17],p),17)

    def test_zero_latency_is_a_valid_measurement(self):
        self.assertEqual(nearest_rank([0,0,1],50),0)

    def test_unmeasured_empty_set_refused(self):
        with self.assertRaises(SupervisedRejected):
            nearest_rank([],95)

    def test_negative_times_refused(self):
        with self.assertRaises(SupervisedRejected):
            nearest_rank([-1,2],50)

    def test_boolean_time_refused(self):
        with self.assertRaises(SupervisedRejected):
            nearest_rank([True,3],50)

    def test_percentile_outside_range_refused(self):
        for value in (0,101,True,1.5):
            with self.subTest(p=value),self.assertRaises(SupervisedRejected):
                nearest_rank([1,2],value)


if __name__=="__main__":
    unittest.main()
