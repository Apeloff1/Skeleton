import unittest
from skeleton.ai.model_runtime.serving_telemetry import RequestTelemetry, ServingTelemetryWindow

class TestServingTelemetry(unittest.TestCase):
    def test_goodput_and_prefix_reuse_are_measured(self):
        window = ServingTelemetryWindow()
        window.record(RequestTelemetry("a", 100, 20, 500, 100, 20, 80))
        window.record(RequestTelemetry("b", 900, 20, 1200, 100, 20, 0))
        metrics = window.metrics(ttft_slo_ms=500, inter_token_slo_ms=50, e2e_slo_ms=1000)
        self.assertEqual(metrics["requests"], 2)
        self.assertEqual(metrics["slo_compliant_requests"], 1)
        self.assertEqual(metrics["goodput_pct"], 50.0)
        self.assertEqual(metrics["prefix_reuse_pct"], 40.0)

    def test_duplicate_request_telemetry_fails_closed(self):
        window = ServingTelemetryWindow()
        record = RequestTelemetry("a", 1, 1, 1, 1, 1)
        window.record(record)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            window.record(record)

    def test_empty_window_is_deterministic(self):
        window = ServingTelemetryWindow()
        left = window.metrics(ttft_slo_ms=1, inter_token_slo_ms=1, e2e_slo_ms=1)
        right = window.metrics(ttft_slo_ms=1, inter_token_slo_ms=1, e2e_slo_ms=1)
        self.assertEqual(left, right)
        self.assertEqual(left["goodput_pct"], 0)
        self.assertEqual(len(left["digest"]), 64)

if __name__ == "__main__":
    unittest.main()
