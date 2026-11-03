"""Resource admission rejects nonexistent models and coerced step counts."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.native_candidate.run_limits import ResourceLimits
from skeleton.ai.runtime.operational_ai.native_candidate.errors import CandidateRejected


class TestCandidateResources(unittest.TestCase):
    def test_valid_bounded_training(self):
        result = ResourceLimits().admit(model_bytes=1048576, steps=200, examples=432,
                                        estimated_working_bytes=20000000)
        self.assertTrue(result["admitted"])
        self.assertFalse(result["device_validated"])

    def test_no_zero_resource_training(self):
        with self.assertRaises(CandidateRejected):
            ResourceLimits().admit(model_bytes=0, steps=0, examples=0,
                                    estimated_working_bytes=0)

    def test_optimizer_overrun(self):
        with self.assertRaises(CandidateRejected):
            ResourceLimits().admit(model_bytes=1048576, steps=16385, examples=432,
                                    estimated_working_bytes=20000000)

    def test_boolean_never_satisfies_integer_bounds(self):
        with self.assertRaises(CandidateRejected):
            ResourceLimits().admit(model_bytes=True, steps=5, examples=100,
                                    estimated_working_bytes=2000000)


if __name__ == "__main__":
    unittest.main()
