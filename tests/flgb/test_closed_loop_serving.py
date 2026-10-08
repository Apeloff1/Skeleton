import unittest
from skeleton.ai.model_runtime.closed_loop_serving import ClosedLoopServingController
from skeleton.ai.model_runtime.runtime_feedback import DeterministicRuntimeEstimator, FeedbackLimits
from skeleton.ai.model_runtime.runtime_policy import RuntimePolicyCompiler
from skeleton.ai.model_runtime.serving_telemetry import RequestTelemetry
from skeleton.ai.model_runtime.slo_planner import RuntimeEstimate, SLOTarget

class TestClosedLoopServing(unittest.TestCase):
    def make(self):
        policy = RuntimePolicyCompiler().compile(2024)
        estimator = DeterministicRuntimeEstimator(
            RuntimeEstimate(500, 50, 20, 8), FeedbackLimits(min_samples=2)
        )
        return ClosedLoopServingController(policy=policy, estimator=estimator)

    def test_feedback_changes_resource_forecast(self):
        controller = self.make()
        slo = SLOTarget(1000, 100, 5000)
        before = controller.decide(
            prompt_tokens=100, slo=slo, kv_capacity_bytes=100000,
            kv_used_bytes=0, queue_pressure_pct=0,
        )
        controller.observe(
            RequestTelemetry("a", 100, 10, 200, 100, 5), kv_bytes_per_token=4
        )
        after = controller.decide(
            prompt_tokens=100, slo=slo, kv_capacity_bytes=100000,
            kv_used_bytes=0, queue_pressure_pct=0,
        )
        self.assertNotEqual(before.feedback_digest, after.feedback_digest)
        self.assertNotEqual(
            before.resource_plan.reserved_kv_bytes,
            after.resource_plan.reserved_kv_bytes,
        )

    def test_policy_identity_cannot_be_changed_by_feedback(self):
        controller = self.make()
        original = controller.policy.digest
        for i in range(5):
            controller.observe(
                RequestTelemetry(str(i), 100, 10, 200, 10, 5), kv_bytes_per_token=4
            )
        self.assertEqual(controller.policy.digest, original)
        decision = controller.decide(
            prompt_tokens=10, slo=SLOTarget(1000, 100, 5000),
            kv_capacity_bytes=10000, kv_used_bytes=0, queue_pressure_pct=0,
        )
        self.assertEqual(decision.policy_digest, original)

    def test_control_decision_is_replay_stable_without_new_observation(self):
        controller = self.make()
        args = dict(
            prompt_tokens=10, slo=SLOTarget(1000, 100, 5000),
            kv_capacity_bytes=10000, kv_used_bytes=0, queue_pressure_pct=0,
        )
        self.assertEqual(controller.decide(**args), controller.decide(**args))

if __name__ == "__main__":
    unittest.main()
