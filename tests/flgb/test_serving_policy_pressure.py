import unittest
from skeleton.ai.model_runtime.runtime_policy import RuntimePolicyCompiler
from skeleton.ai.model_runtime.serving_policy import PolicyAwareServingPlanner, ServiceClass, ServingRequest

class TestServingPolicyPressure(unittest.TestCase):
    def test_kv_pressure_collapses_disaggregation(self):
        policy = RuntimePolicyCompiler().compile(2024, requested=("phase_disaggregation",))
        plan = PolicyAwareServingPlanner(policy).plan(
            ServingRequest("r", 2048, 64), kv_pressure_pct=95
        )
        self.assertEqual(plan.phase_mode, "unified")
        self.assertIn("collapse_phase_disaggregation_under_kv_pressure", plan.degradation)

    def test_queue_pressure_protects_interactive(self):
        planner = PolicyAwareServingPlanner(RuntimePolicyCompiler().compile(2024))
        interactive = planner.plan(
            ServingRequest("i", 10, 10, ServiceClass.INTERACTIVE), queue_pressure_pct=99
        )
        background = planner.plan(
            ServingRequest("b", 10, 10, ServiceClass.BACKGROUND), queue_pressure_pct=99
        )
        self.assertGreater(interactive.priority_boost, 100)
        self.assertLess(background.priority_boost, -25)

    def test_receipt_is_stable_and_policy_bound(self):
        policy = RuntimePolicyCompiler().compile(2024)
        planner = PolicyAwareServingPlanner(policy)
        request = ServingRequest("r", 100, 20, prefix_tokens=50, prefix_cached=True)
        left = planner.plan(request, kv_pressure_pct=20, queue_pressure_pct=30)
        right = planner.plan(request, kv_pressure_pct=20, queue_pressure_pct=30)
        self.assertEqual(left, right)
        self.assertEqual(left.policy_digest, policy.digest)
        self.assertEqual(len(left.digest), 64)

    def test_invalid_pressure_fails_closed(self):
        planner = PolicyAwareServingPlanner(RuntimePolicyCompiler().compile(2024))
        with self.assertRaises(ValueError):
            planner.plan(ServingRequest("r", 1, 1), kv_pressure_pct=101)

    def test_speculative_decode_requires_validated_opt_in_and_draft(self):
        capability = "speculative_decoding"
        base = PolicyAwareServingPlanner(RuntimePolicyCompiler().compile(2024))
        req = ServingRequest("s", 20, 32, draft_model_available=True)
        self.assertFalse(base.plan(req).speculative)
        enabled = PolicyAwareServingPlanner(
            RuntimePolicyCompiler().compile(2024, requested=(capability,))
        )
        self.assertTrue(enabled.plan(req).speculative)
        no_draft = ServingRequest("n", 20, 32, draft_model_available=False)
        self.assertFalse(enabled.plan(no_draft).speculative)

    def test_kv_pressure_disables_speculation(self):
        capability = "speculative_decoding"
        planner = PolicyAwareServingPlanner(
            RuntimePolicyCompiler().compile(2024, requested=(capability,))
        )
        req = ServingRequest("s", 20, 32, draft_model_available=True)
        plan = planner.plan(req, kv_pressure_pct=95)
        self.assertFalse(plan.speculative)
        self.assertIn("disable_speculative_under_kv_pressure", plan.degradation)

if __name__ == "__main__":
    unittest.main()
