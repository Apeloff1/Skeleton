"""Regression: canonical playable registration of already-built reference engines."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_engine_bindings import MODULES
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ACTION_HELP, ENGINES, AdvancedRuntimeError, run_advanced_session,
    verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError, make_advanced_scene, validate_advanced_scene,
)
from skeleton.ai.game_builder.system_editors import catalog


class NewlyBoundEngineTests(unittest.TestCase):
    def test_canonical_registration_and_deterministic_replay(self):
        specs = {spec["id"]: spec for spec in catalog()}
        for engine, module in MODULES.items():
            with self.subTest(engine=engine):
                self.assertIn(engine, ENGINES)
                self.assertEqual(specs[engine]["runtime_maturity"], "advanced_reference_runtime")
                self.assertEqual(tuple(ACTION_HELP[engine]), tuple(module.ACTIONS))
                source = make_advanced_scene(engine, seed=3)
                self.assertEqual(source, validate_advanced_scene(source))
                a = run_advanced_session(engine, seed=3, scene=source, actions=["inspect"])
                b = run_advanced_session(engine, seed=3, scene=source, actions=["inspect"])
                self.assertEqual(a, b)
                self.assertTrue(verify_advanced_session(a))
                self.assertEqual(a["validated_turn_count"], 1)
                self.assertFalse(a["native_hardware_verified"])
                altered = deepcopy(a)
                altered["state"]["finished"] = not altered["state"]["finished"]
                with self.assertRaises(AdvancedRuntimeError):
                    verify_advanced_session(altered)

    def test_invalid_actions_and_tampered_scene_rejected(self):
        for engine in MODULES:
            with self.subTest(engine=engine):
                with self.assertRaises(AdvancedRuntimeError):
                    run_advanced_session(engine, actions=["!unregistered!"])
                scene = make_advanced_scene(engine)
                scene["layout"]["title"] = "Tampered source"
                with self.assertRaises(SceneError):
                    run_advanced_session(engine, scene=scene)


if __name__ == "__main__":
    unittest.main()
