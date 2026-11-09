import unittest

from skeleton.ai.model_runtime.runtime_signals import (
    RuntimeSignal,
    RuntimeSignalRegistry,
    SignalMaturity,
)


class TestRuntimeSignals(unittest.TestCase):
    def test_policy_accumulates_only_mature_defaults_by_year(self):
        registry = RuntimeSignalRegistry()
        self.assertEqual(
            registry.production_policy(2023),
            ("iteration_level_scheduling", "paged_kv_memory"),
        )
        self.assertEqual(
            registry.production_policy(2024),
            (
                "iteration_level_scheduling",
                "paged_kv_memory",
                "chunked_prefill",
                "tiered_kv_reuse",
                "prefix_affinity",
                "slo_admission",
            ),
        )
        self.assertEqual(registry.production_policy(2026), registry.production_policy(2024))

    def test_2026_experimental_signals_are_candidates_not_defaults(self):
        registry = RuntimeSignalRegistry()
        candidates = {signal.capability: signal.maturity for signal in registry.candidates(2026)}
        self.assertEqual(
            candidates["attention_ffn_phase_specialization"],
            SignalMaturity.EXPERIMENTAL,
        )
        self.assertEqual(
            candidates["disaggregated_quantization"],
            SignalMaturity.EXPERIMENTAL,
        )

    def test_emerging_signal_cannot_be_default(self):
        with self.assertRaisesRegex(ValueError, "cannot be a production default"):
            RuntimeSignal(
                "unsafe-new-default",
                2026,
                "unvalidated_capability",
                SignalMaturity.EXPERIMENTAL,
                "research-only",
                True,
            )

    def test_snapshot_is_deterministic_and_year_bounded(self):
        registry = RuntimeSignalRegistry()
        left = registry.snapshot(2024)
        right = registry.snapshot(2024)
        self.assertEqual(left, right)
        self.assertEqual(len(left["digest"]), 64)
        self.assertTrue(all(item["year"] <= 2024 for item in left["signals"]))
        self.assertFalse(any(item["year"] == 2026 for item in left["signals"]))

    def test_duplicate_signal_ids_fail_closed(self):
        signal = RuntimeSignal(
            "duplicate", 2024, "x", SignalMaturity.VALIDATED, "fixture"
        )
        with self.assertRaisesRegex(ValueError, "duplicate runtime signal identity"):
            RuntimeSignalRegistry((signal, signal))


if __name__ == "__main__":
    unittest.main()
