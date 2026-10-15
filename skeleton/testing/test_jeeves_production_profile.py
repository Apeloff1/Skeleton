"""Profile-selection contracts: no silently upscaled or downgraded Jeeves."""
from __future__ import annotations

import importlib.util
import os
import unittest
from unittest.mock import patch

from skeleton.cortex.production_profile import (
    PROFILES, build_initial_speaking_model, configured_profile,
)


class JeevesProductionProfileTests(unittest.TestCase):
    def test_default_is_unmodified_legacy_capacity(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            profile = configured_profile()
            self.assertEqual(profile.name, "legacy")
            self.assertEqual((profile.dim, profile.context, profile.layers), (8, 8, 2))

    def test_unrecognized_profile_fails_closed(self) -> None:
        with patch.dict(os.environ, {"SKELETON_JEEVES_PROFILE": "unknown"}):
            with self.assertRaisesRegex(ValueError, "unsupported"):
                configured_profile()

    def test_profile_tiers_are_explicit(self) -> None:
        self.assertEqual(set(PROFILES), {"legacy", "mobile", "desktop", "workstation"})
        for tier in PROFILES.values():
            self.assertGreaterEqual(tier.feedforward, tier.dim)
            self.assertEqual(tier.dim % tier.heads, 0)

    @unittest.skipUnless(importlib.util.find_spec("torch"), "torch optional")
    def test_small_torch_profile_constructs_expected_architecture(self) -> None:
        from skeleton.cortex.torch_lm import TorchTransformer
        with patch.dict(os.environ, {
            "SKELETON_JEEVES_PROFILE": "mobile",
            "SKELETON_JEEVES_DEVICE": "cpu",
        }):
            model = build_initial_speaking_model(vocab=("quest", "dialogue", "world"))
        self.assertIsInstance(model, TorchTransformer)
        self.assertEqual((model.dim, model.ctx, model.n_layers), (32, 64, 2))
        self.assertEqual(model.snapshot()["kind"], "torch-stack")

    @unittest.skipUnless(importlib.util.find_spec("torch"), "torch optional")
    def test_invalid_or_missing_accelerator_is_not_hidden(self) -> None:
        from skeleton.cortex.production_profile import _torch_device
        with patch.dict(os.environ, {"SKELETON_JEEVES_DEVICE": "bad-gpu"}):
            with self.assertRaisesRegex(ValueError, "must be"):
                _torch_device()


if __name__ == "__main__":
    unittest.main()
