import unittest

from skeleton.ai.model_runtime.runtime_policy import RuntimePolicyCompiler


class TestRuntimePolicyCompiler(unittest.TestCase):
    def setUp(self):
        self.compiler = RuntimePolicyCompiler()

    def test_2023_policy_contains_only_2023_defaults(self):
        policy = self.compiler.compile(2023)
        self.assertTrue(policy.allows("iteration_level_scheduling"))
        self.assertTrue(policy.allows("paged_kv_memory"))
        self.assertFalse(policy.allows("prefix_affinity"))
        self.assertEqual(policy.experimental, ())

    def test_2024_validated_defaults_compile_without_override(self):
        policy = self.compiler.compile(2024)
        self.assertTrue(policy.allows("prefix_affinity"))
        self.assertTrue(policy.allows("tiered_kv_reuse"))
        self.assertFalse(policy.allows("phase_disaggregation"))

    def test_validated_opt_in_is_allowed(self):
        policy = self.compiler.compile(2024, requested=("phase_disaggregation",))
        self.assertTrue(policy.allows("phase_disaggregation"))
        self.assertNotIn("phase_disaggregation", policy.experimental)

    def test_future_signal_cannot_leak_into_historical_policy(self):
        with self.assertRaisesRegex(ValueError, "unavailable through 2024"):
            self.compiler.compile(
                2024,
                requested=("attention_ffn_phase_specialization",),
                enable_experimental=("attention_ffn_phase_specialization",),
            )

    def test_2026_experimental_signal_requires_double_consent(self):
        capability = "attention_ffn_phase_specialization"
        with self.assertRaisesRegex(ValueError, "explicit experimental enablement"):
            self.compiler.compile(2026, requested=(capability,))
        policy = self.compiler.compile(
            2026,
            requested=(capability,),
            enable_experimental=(capability,),
        )
        self.assertIn(capability, policy.experimental)
        self.assertTrue(policy.allows(capability))

    def test_unrequested_experimental_enablement_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "was not requested"):
            self.compiler.compile(
                2026,
                enable_experimental=("disaggregated_quantization",),
            )

    def test_policy_receipt_is_replay_stable(self):
        left = self.compiler.compile(2026)
        right = self.compiler.compile(2026)
        self.assertEqual(left, right)
        self.assertEqual(len(left.digest), 64)


if __name__ == "__main__":
    unittest.main()
