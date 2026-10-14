import unittest

from skeleton.ai.model_runtime.temporal_policy import TemporalRuntimePolicyCompiler


class TestTemporalRuntimePolicy(unittest.TestCase):
    def setUp(self):
        self.compiler = TemporalRuntimePolicyCompiler()

    def test_2026_binds_2020_epoch_and_year_policy(self):
        policy = self.compiler.compile(2026)
        self.assertEqual(policy.year, 2026)
        self.assertEqual(policy.decade, 2020)
        self.assertIn("transformer_attention", policy.inherited_capabilities)
        self.assertIn("foundation_models", policy.inherited_capabilities)
        self.assertTrue(policy.runtime_policy.allows("paged_kv_memory"))
        self.assertEqual(len(policy.epoch_digest), 64)
        self.assertEqual(len(policy.digest), 64)

    def test_2019_replay_has_no_modern_serving_policy(self):
        policy = self.compiler.compile(2019)
        self.assertEqual(policy.decade, 2010)
        self.assertIn("transformer_attention", policy.inherited_capabilities)
        self.assertNotIn("foundation_models", policy.inherited_capabilities)
        self.assertEqual(policy.runtime_policy.capabilities, ())

    def test_pre_2020_modern_request_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unavailable before 2020"):
            self.compiler.compile(2018, requested=("prefix_affinity",))

    def test_2026_experimental_still_requires_year_gate(self):
        capability = "disaggregated_quantization"
        with self.assertRaisesRegex(ValueError, "explicit experimental enablement"):
            self.compiler.compile(2026, requested=(capability,))
        policy = self.compiler.compile(
            2026,
            requested=(capability,),
            enable_experimental=(capability,),
        )
        self.assertIn(capability, policy.runtime_policy.experimental)

    def test_temporal_receipt_is_replay_stable(self):
        self.assertEqual(self.compiler.compile(2026), self.compiler.compile(2026))


if __name__ == "__main__":
    unittest.main()
