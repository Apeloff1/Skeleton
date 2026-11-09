"""Cinematic timing and interactive branch reference execution."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    AdvancedRuntimeError, ENGINES, run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError, make_advanced_scene,
)
from skeleton.jeeves.game_studio_environment import (
    make_studio_source, StudioGameEnvironment,
)


class CinematicTimelineTests(unittest.TestCase):
    def test_actual_timeline_cut_timing_cues_and_completion(self):
        self.assertIn("cinematics", ENGINES)
        settings={"shots":2,"max_shot_seconds":5,"camera_rigs":2}
        layout={"title":"Original Two-Shot Ending","shot_count":2,
                "timing_seed":1,
                "overrides":[
                    {"shot":0,"rig":0,"duration":2,
                     "cue":"actor","interactive":False},
                    {"shot":1,"rig":1,"duration":3,
                     "cue":"decision","interactive":True},
                ]}
        scene=make_advanced_scene("cinematics",settings,seed=3,layout=layout)
        actions=["cue","camera:1","tick:4","cue","choose:2",
                 "tick:4","finish"]
        result=run_advanced_session("cinematics",settings,actions,seed=3,
                                    scene=scene)
        self.assertTrue(result["state"]["finished"])
        self.assertEqual(result["state"]["timeline_seconds"],5)
        self.assertEqual(result["state"]["played_shots"],[0,1])
        self.assertEqual(result["state"]["choices"][0]["choice"],2)
        self.assertEqual(len(result["state"]["cues"]),2)
        self.assertTrue(verify_advanced_session(result,settings))

    def test_interactive_unearned_cut_rejected_and_tampered_scene_fails(self):
        settings={"shots":2,"max_shot_seconds":5}
        scene=make_advanced_scene("cinematics",settings,layout={
            "title":"Original Actor Branch","shot_count":2,"timing_seed":0,
            "overrides":[
                {"shot":0,"rig":0,"duration":1,"cue":"actor","interactive":True},
            ],
        })
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("cinematics",settings,["skip"],scene=scene)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("cinematics",settings,["finish"],scene=scene)
        scene["layout"]["overrides"][0]["duration"]=999
        with self.assertRaises(SceneError):
            run_advanced_session("cinematics",settings,scene=scene)

    def test_learning_adapter_exposes_actual_timeline_not_fake_pixels(self):
        source=make_studio_source("cinematics",{"shots":3},
                                  actions=("inspect","tick:16","cue"))
        env=StudioGameEnvironment(source,max_steps=10)
        env.reset(7)
        move=env.step("tick:16")
        self.assertEqual(move.info["runtime_kind"],"original_game_reference_runtime")
        self.assertFalse(env.preview()["pixel_frame_available"])
        self.assertGreaterEqual(env._receipt["state"]["timeline_seconds"],1)


if __name__=="__main__":
    unittest.main()
