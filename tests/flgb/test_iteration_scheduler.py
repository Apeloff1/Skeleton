import unittest
from skeleton.ai.model_runtime.iteration_scheduler import InferencePhase, IterationScheduler, IterationWork

class TestIterationScheduler(unittest.TestCase):
    def test_decode_gets_latency_protection_over_large_prefill(self):
        scheduler = IterationScheduler(token_budget=513, prefill_quantum=512)
        plan = scheduler.plan((
            IterationWork("prefill", InferencePhase.PREFILL, 4000),
            IterationWork("decode", InferencePhase.DECODE, 100),
        ))
        self.assertEqual(plan.slices[0].request_id, "decode")
        self.assertEqual(plan.slices[0].tokens, 1)
        self.assertEqual(plan.slices[1].tokens, 512)

    def test_prefill_is_chunked_by_quantum(self):
        plan = IterationScheduler(token_budget=2048, prefill_quantum=256).plan((
            IterationWork("p", InferencePhase.PREFILL, 1000),
        ))
        self.assertEqual(plan.slices[0].tokens, 256)

    def test_age_can_overcome_decode_bias(self):
        scheduler = IterationScheduler(
            token_budget=1, prefill_quantum=1, decode_priority_boost=10, max_age_boost=100
        )
        plan = scheduler.plan((
            IterationWork("old-prefill", InferencePhase.PREFILL, 10, age=50),
            IterationWork("decode", InferencePhase.DECODE, 10, age=0),
        ))
        self.assertEqual(plan.slices[0].request_id, "old-prefill")

    def test_duplicate_request_identity_fails_closed(self):
        scheduler = IterationScheduler()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            scheduler.plan((
                IterationWork("x", InferencePhase.PREFILL, 1),
                IterationWork("x", InferencePhase.DECODE, 1),
            ))

    def test_plan_is_replay_stable(self):
        scheduler = IterationScheduler(token_budget=100)
        work = (
            IterationWork("a", InferencePhase.PREFILL, 50),
            IterationWork("b", InferencePhase.DECODE, 20),
        )
        self.assertEqual(scheduler.plan(work), scheduler.plan(work))

if __name__ == "__main__":
    unittest.main()
