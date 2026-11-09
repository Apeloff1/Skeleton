import unittest
from skeleton.ai.model_runtime.slo_planner import RuntimeEstimate, SLOResourcePlanner, SLOTarget

class TestSLOResourcePlanner(unittest.TestCase):
    def setUp(self):
        self.planner = SLOResourcePlanner(prefill_chunk_tokens=512, overload_reject_pct=95)
        self.slo = SLOTarget(ttft_ms=500, inter_token_ms=50, end_to_end_ms=3000)

    def test_long_prefill_is_chunked_without_token_loss(self):
        plan = self.planner.plan(
            prompt_tokens=1300,
            estimate=RuntimeEstimate(400, 20, 20, 4),
            slo=self.slo, kv_capacity_bytes=10000, kv_used_bytes=0, queue_pressure_pct=20,
        )
        self.assertEqual(plan.prefill_chunks, (512, 512, 276))
        self.assertEqual(sum(plan.prefill_chunks), 1300)
        self.assertTrue(plan.admitted)

    def test_predicted_kv_is_reserved_for_prompt_and_output(self):
        plan = self.planner.plan(
            prompt_tokens=100,
            estimate=RuntimeEstimate(100, 10, 50, 8),
            slo=self.slo, kv_capacity_bytes=10000, kv_used_bytes=0, queue_pressure_pct=0,
        )
        self.assertEqual(plan.reserved_kv_bytes, 1200)

    def test_insufficient_kv_rejects_before_execution(self):
        plan = self.planner.plan(
            prompt_tokens=100,
            estimate=RuntimeEstimate(100, 10, 50, 8),
            slo=self.slo, kv_capacity_bytes=1000, kv_used_bytes=0, queue_pressure_pct=0,
        )
        self.assertFalse(plan.admitted)
        self.assertEqual(plan.reason, "insufficient_predicted_kv_capacity")

    def test_overload_rejects_predicted_slo_miss(self):
        plan = self.planner.plan(
            prompt_tokens=100,
            estimate=RuntimeEstimate(900, 100, 50, 1),
            slo=self.slo, kv_capacity_bytes=10000, kv_used_bytes=0, queue_pressure_pct=99,
        )
        self.assertFalse(plan.admitted)
        self.assertFalse(plan.slo_compliant)
        self.assertEqual(plan.reason, "overload_predicted_slo_miss")

    def test_non_overloaded_slo_miss_is_observable_not_silently_rejected(self):
        plan = self.planner.plan(
            prompt_tokens=100,
            estimate=RuntimeEstimate(900, 100, 50, 1),
            slo=self.slo, kv_capacity_bytes=10000, kv_used_bytes=0, queue_pressure_pct=10,
        )
        self.assertTrue(plan.admitted)
        self.assertFalse(plan.slo_compliant)

    def test_plan_digest_is_stable(self):
        args = dict(
            prompt_tokens=100, estimate=RuntimeEstimate(100, 10, 10, 2),
            slo=self.slo, kv_capacity_bytes=10000, kv_used_bytes=100, queue_pressure_pct=5,
        )
        self.assertEqual(self.planner.plan(**args), self.planner.plan(**args))

if __name__ == "__main__":
    unittest.main()
