import unittest
from skeleton.ai.model_runtime.runtime_policy import RuntimePolicyCompiler
from skeleton.ai.model_runtime.serving_policy import PolicyAwareServingPlanner, ServingRequest

class TestServingPolicyEra(unittest.TestCase):
    def test_2023_does_not_reuse_2024_prefix_signal(self):
        planner = PolicyAwareServingPlanner(RuntimePolicyCompiler().compile(2023))
        plan = planner.plan(ServingRequest("r", 100, 10, prefix_tokens=80, prefix_cached=True))
        self.assertEqual(plan.prefix_reused_tokens, 0)
        self.assertEqual(plan.prefill_tokens, 100)

    def test_2024_prefix_affinity_reduces_prefill(self):
        planner = PolicyAwareServingPlanner(RuntimePolicyCompiler().compile(2024))
        plan = planner.plan(ServingRequest("r", 100, 10, prefix_tokens=80, prefix_cached=True))
        self.assertEqual(plan.prefix_reused_tokens, 80)
        self.assertEqual(plan.prefill_tokens, 20)

    def test_phase_disaggregation_is_explicit(self):
        policy = RuntimePolicyCompiler().compile(2024, requested=("phase_disaggregation",))
        planner = PolicyAwareServingPlanner(policy)
        self.assertEqual(planner.plan(ServingRequest("small", 100, 10)).phase_mode, "unified")
        self.assertEqual(planner.plan(ServingRequest("large", 2048, 10)).phase_mode, "disaggregated")

if __name__ == "__main__":
    unittest.main()
