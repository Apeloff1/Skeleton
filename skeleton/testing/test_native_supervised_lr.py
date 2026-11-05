"""Exact bounded cosine SGD schedule, never inferred from static fixture count."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.native_supervised.lr_schedule import learning_rate
from skeleton.ai.runtime.operational_ai.native_supervised.errors import SupervisedRejected


class TestActualNativeSGDSchedule(unittest.TestCase):
    def test_endpoints_and_floor(self):
        self.assertAlmostEqual(learning_rate(0,10,10000,floor_ppm=1000),0.01)
        self.assertAlmostEqual(learning_rate(9,10,10000,floor_ppm=1000),0.001)

    def test_monotone_cosine(self):
        values=[learning_rate(i,100,10000,floor_ppm=100)
                for i in range(100)]
        self.assertTrue(all(values[i]>=values[i+1] for i in range(99)))

    def test_bounds_are_finite(self):
        for rate in [learning_rate(i,16,10000,floor_ppm=100) for i in range(16)]:
            self.assertGreater(rate,0)
            self.assertLessEqual(rate,0.01)

    def test_no_step_overflow(self):
        with self.assertRaises(SupervisedRejected):
            learning_rate(10,10,10000)

    def test_no_invalid_boolean(self):
        with self.assertRaises(SupervisedRejected):
            learning_rate(True,10,10000)

    def test_floor_cannot_exceed_base(self):
        with self.assertRaises(SupervisedRejected):
            learning_rate(0,10,1000,floor_ppm=2000)


if __name__=="__main__":
    unittest.main()
