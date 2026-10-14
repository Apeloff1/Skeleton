import unittest
from skeleton.ai.model_runtime.runtime_feedback import DeterministicRuntimeEstimator, FeedbackLimits
from skeleton.ai.model_runtime.serving_telemetry import RequestTelemetry
from skeleton.ai.model_runtime.slo_planner import RuntimeEstimate

class TestRuntimeFeedback(unittest.TestCase):
    def make(self):
        return DeterministicRuntimeEstimator(
            RuntimeEstimate(400, 40, 20, 8),
            FeedbackLimits(min_samples=2, max_samples=4, max_observation_ms=1000),
        )

    def test_feedback_requires_sample_floor(self):
        estimator = self.make()
        self.assertFalse(estimator.ready)
        estimator.observe(RequestTelemetry("a", 200, 20, 500, 10, 10), kv_bytes_per_token=4)
        self.assertFalse(estimator.ready)
        receipt = estimator.observe(
            RequestTelemetry("b", 200, 20, 500, 10, 10), kv_bytes_per_token=4
        )
        self.assertTrue(receipt.ready)

    def test_integer_ewma_is_replay_deterministic(self):
        observations = (
            RequestTelemetry("a", 200, 20, 500, 10, 10),
            RequestTelemetry("b", 300, 30, 600, 10, 12),
        )
        left, right = self.make(), self.make()
        for item in observations:
            left.observe(item, kv_bytes_per_token=4)
            right.observe(item, kv_bytes_per_token=4)
        self.assertEqual(left.receipt(), right.receipt())

    def test_extreme_latency_is_clipped(self):
        estimator = self.make()
        receipt = estimator.observe(
            RequestTelemetry("a", 999999, 999999, 999999, 1, 1), kv_bytes_per_token=4
        )
        self.assertEqual(receipt.clipped_observations, 2)
        self.assertLessEqual(receipt.estimate.prefill_ms, 1000)
        self.assertLessEqual(receipt.estimate.decode_token_ms, 1000)

    def test_sample_counter_is_bounded(self):
        estimator = self.make()
        for i in range(10):
            estimator.observe(
                RequestTelemetry(str(i), 100, 10, 200, 1, 1), kv_bytes_per_token=4
            )
        self.assertEqual(estimator.receipt().samples, 4)

    def test_receipt_has_stable_identity(self):
        estimator = self.make()
        self.assertEqual(estimator.receipt(), estimator.receipt())
        self.assertEqual(len(estimator.receipt().digest), 64)

if __name__ == "__main__":
    unittest.main()
