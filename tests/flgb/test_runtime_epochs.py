import unittest

from skeleton.ai.model_runtime.runtime_epochs import (
    EpochStatus,
    RuntimeEpoch,
    RuntimeEpochRegistry,
)


class TestRuntimeEpochs(unittest.TestCase):
    def test_capabilities_inherit_across_decades(self):
        registry = RuntimeEpochRegistry()
        caps_1990 = set(registry.inherited_capabilities(1990))
        caps_2020 = set(registry.inherited_capabilities(2020))
        self.assertLess(caps_1990, caps_2020)
        self.assertIn("statistical_nlp", caps_1990)
        self.assertIn("transformer_attention", caps_2020)
        self.assertIn("paged_kv_memory", caps_2020)

    def test_future_forecasts_do_not_enter_default_inheritance(self):
        registry = RuntimeEpochRegistry()
        caps = registry.inherited_capabilities(2040)
        self.assertNotIn("verified_self_optimization", caps)
        self.assertNotIn("persistent_world_simulation", caps)

    def test_forecast_requires_explicit_snapshot_mode(self):
        registry = RuntimeEpochRegistry()
        default = registry.snapshot(2040)
        forecast = registry.snapshot(2040, include_forecast=True)
        self.assertFalse(any(e["status"] == "forecast" for e in default["epochs"]))
        self.assertTrue(any(e["status"] == "forecast" for e in forecast["epochs"]))
        self.assertNotEqual(default["digest"], forecast["digest"])

    def test_historical_cutoff_blocks_future_decades(self):
        registry = RuntimeEpochRegistry()
        snapshot = registry.snapshot(2000)
        self.assertTrue(all(epoch["decade"] <= 2000 for epoch in snapshot["epochs"]))
        caps = set(registry.inherited_capabilities(2000))
        self.assertNotIn("transformer_attention", caps)
        self.assertNotIn("foundation_models", caps)

    def test_invalid_decade_fails_closed(self):
        registry = RuntimeEpochRegistry()
        with self.assertRaisesRegex(ValueError, "decade boundary"):
            registry.snapshot(2026)

    def test_forecast_cannot_relabel_historical_decade(self):
        with self.assertRaisesRegex(ValueError, "historical decade cannot be forecast"):
            RuntimeEpoch(2010, EpochStatus.FORECAST, ("x",), "invalid")

    def test_epoch_receipt_is_replay_stable(self):
        registry = RuntimeEpochRegistry()
        self.assertEqual(registry.snapshot(2020), registry.snapshot(2020))
        self.assertEqual(len(registry.snapshot(2020)["digest"]), 64)


if __name__ == "__main__":
    unittest.main()
