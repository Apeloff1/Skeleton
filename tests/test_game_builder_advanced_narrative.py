"""Original authored story: real branch consequences and replay custody."""
from __future__ import annotations
from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ACTION_HELP, ENGINES, AdvancedRuntimeError, run_advanced_session,
    verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError, make_advanced_scene,
)
from skeleton.ai.game_builder.advanced_narrative_runtime import ACTIONS
from skeleton.jeeves.game_studio_environment import (
    make_studio_source, StudioGameEnvironment,
)


class NarrativeGameTests(unittest.TestCase):
    def test_real_branch_and_distinct_earned_endings(self):
        self.assertIn("narrative", ENGINES)
        self.assertEqual(set(ACTIONS), set(ACTION_HELP["narrative"]))
        config = {"branch_depth": 3, "ending_count": 5,
                  "state_flags": 16, "postgame_play": True}
        a = run_advanced_session(
            "narrative", config, ["choose:0"] * 3 +
            ["checkpoint", "resolve", "explore", "retire"], seed=5,
        )
        b = run_advanced_session(
            "narrative", config, ["choose:1"] * 3 +
            ["checkpoint", "resolve"], seed=5,
        )
        self.assertTrue(a["state"]["completed"])
        self.assertTrue(a["state"]["finished"])
        self.assertTrue(b["state"]["completed"])
        self.assertNotEqual(a["state"]["flags"], b["state"]["flags"])
        self.assertNotEqual(a["state"]["faction"], b["state"]["faction"])
        self.assertTrue(verify_advanced_session(a, config))
        self.assertTrue(verify_advanced_session(b, config))

    def test_finite_source_and_unearned_endings_rejected(self):
        source = make_advanced_scene("narrative", seed=8)
        result = run_advanced_session("narrative", seed=8, scene=source,
                                      actions=["choose:1", "review"])
        self.assertTrue(verify_advanced_session(result))
        self.assertEqual(result["state"]["beat"], 1)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("narrative", actions=["resolve"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("narrative",
                {"structure": "linear"}, actions=["choose:1"])
        source["layout"]["beats"][0]["theme"] = "borrowed_game_title"
        with self.assertRaises(SceneError):
            run_advanced_session("narrative", seed=8, scene=source)

    def test_replay_bound_learning_environment(self):
        studio = StudioGameEnvironment(make_studio_source(
            "narrative", {"branch_depth": 2}, actions=("choose:0", "review")))
        studio.reset(55)
        move = studio.step("choose:0")
        self.assertEqual(move.info["evidence"]["accepted"], True)
        self.assertGreater(studio._receipt["state"]["trust"] +
                           studio._receipt["state"]["knowledge"] +
                           studio._receipt["state"]["power"], 0)
        snapshot = studio.snapshot()
        clone = StudioGameEnvironment(studio.source)
        # max_steps is part of environment source identity.
        clone = StudioGameEnvironment(studio.source, max_steps=64)
        clone.restore(snapshot)
        self.assertEqual(snapshot, clone.snapshot())


if __name__ == "__main__":
    unittest.main()
