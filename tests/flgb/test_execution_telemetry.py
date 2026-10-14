import unittest
from skeleton.ai.model_runtime.execution_telemetry import ExecutionTiming

class TestExecutionTelemetry(unittest.TestCase):
    def test_timing_converts_to_integer_serving_metrics(self):
        timing = ExecutionTiming(
            "r", 1_000_000_000, 1_100_000_000, 1_500_000_000,
            output_tokens=5, prompt_tokens=100, prefix_reused_tokens=60,
        )
        telemetry = timing.telemetry()
        self.assertEqual(telemetry.ttft_ms, 100)
        self.assertEqual(telemetry.inter_token_ms, 100)
        self.assertEqual(telemetry.e2e_ms, 500)
        self.assertEqual(telemetry.prefix_reused_tokens, 60)

    def test_single_token_decode_has_defined_interval(self):
        timing = ExecutionTiming("r", 0, 10_000_000, 10_000_000, 1, 1)
        self.assertEqual(timing.telemetry().inter_token_ms, 0)

    def test_timestamp_inversion_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "timestamps"):
            ExecutionTiming("r", 10, 5, 20, 1, 1)

    def test_zero_output_tokens_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "output_tokens"):
            ExecutionTiming("r", 0, 0, 0, 0, 1)

if __name__ == "__main__":
    unittest.main()
