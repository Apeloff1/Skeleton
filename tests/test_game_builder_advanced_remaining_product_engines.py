"""Replay-verifiable executable product/editor subsystem rules."""
from __future__ import annotations

import unittest
from copy import deepcopy

from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES, AdvancedRuntimeError, run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError, make_advanced_scene, validate_advanced_scene,
)
from skeleton.ai.game_builder.advanced_localization_runtime import default_layout
from skeleton.ai.game_builder.system_editors import make_editor_document
from skeleton.jeeves.game_studio_environment import (
    StudioGameEnvironment, make_studio_source,
)


class ProductReferenceTests(unittest.TestCase):
    def test_real_hud_control_navigation(self):
        session=run_advanced_session("ui_hud",actions=[
            "right","select","hint","open:map","back","finish"
        ],seed=1)
        state=session["state"]
        self.assertTrue(state["finished"])
        self.assertEqual(state["menu_stack"],["root"])
        self.assertEqual(state["navigation_steps"],1)
        self.assertEqual(state["selected"][0]["control"],"inventory")
        self.assertTrue(verify_advanced_session(session))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("ui_hud",actions=["back"])

    def test_accessible_input_remapping_and_secondary_cues(self):
        session=run_advanced_session("accessibility",actions=[
            "remap:jump:confirm","trigger:confirm","cue:visual",
            "show:subtitle","review","finish"
        ],seed=2)
        state=session["state"]
        self.assertEqual(state["mapping"]["jump"],"confirm")
        self.assertEqual(state["dispatches"][0]["logical"],"jump")
        self.assertTrue(state["subtitle_log"])
        self.assertTrue(state["finished"])
        self.assertTrue(verify_advanced_session(session))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("accessibility",{"full_remap":False},
                                 ["remap:jump:confirm"])

    def test_multilingual_plurals_and_explicit_fallback(self):
        cfg={"language_count":4,"text_keys":3}
        ar=run_advanced_session("localization",cfg,[
            "lang:ar","count:2","show:welcome","audit","finish"
        ],seed=1)
        self.assertEqual(ar["state"]["text_direction"],"rtl")
        self.assertIn("عنصران",ar["state"]["rendered"][0]["text"])
        self.assertTrue(verify_advanced_session(ar,cfg))
        source=default_layout(make_editor_document("localization",cfg)["settings"],0)
        source["locales"][1]["strings"].pop("warning")
        scene=make_advanced_scene("localization",cfg,seed=0,layout=source)
        fallback=run_advanced_session("localization",cfg,[
            "lang:fr","show:warning","audit","finish"
        ],seed=0,scene=scene)
        self.assertEqual(fallback["state"]["fallback_count"],1)
        self.assertEqual(fallback["state"]["missing"],1)
        self.assertTrue(verify_advanced_session(fallback,cfg))
        strict={**cfg,"fallback":"block_release"}
        strict_scene=make_advanced_scene("localization",strict,seed=0,layout=source)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("localization",strict,[
                "lang:fr","show:warning"
            ],seed=0,scene=strict_scene)

    def test_era_memory_budget_and_real_logical_frames(self):
        session=run_advanced_session("platform_profile",actions=[
            "spawn:10","stream:4","frame:8","profile","despawn:1",
            "unstream:4","finish"
        ],seed=3)
        state=session["state"]
        self.assertTrue(state["finished"])
        self.assertEqual(state["npc_count"],9)
        self.assertEqual(state["asset_chunks"],0)
        self.assertEqual(state["frames"],8)
        self.assertFalse(state["hardware_measured"])
        self.assertTrue(verify_advanced_session(session))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("platform_profile",
                                 {"ram_budget_mb":1},["spawn:1"])

    def test_scene_custody_and_learning_environment_for_all_four(self):
        for editor in ("ui_hud","accessibility","localization","platform_profile"):
            with self.subTest(editor=editor):
                self.assertIn(editor,ENGINES)
                scene=make_advanced_scene(editor,seed=13)
                receipt=run_advanced_session(editor,actions=["inspect"],seed=13,
                                             scene=scene)
                self.assertTrue(verify_advanced_session(receipt))
                source=make_studio_source(editor,actions=("inspect",))
                env=StudioGameEnvironment(source,max_steps=4)
                env.reset(2**43)
                move=env.step("inspect")
                self.assertTrue(move.info["evidence"]["accepted"])
                snapshot=env.snapshot()
                clone=StudioGameEnvironment(source,max_steps=4)
                clone.restore(snapshot)
                self.assertEqual(clone.snapshot(),snapshot)
                changed=deepcopy(scene)
                changed["layout"]["title"]="tampered"
                with self.assertRaises(SceneError):
                    validate_advanced_scene(changed)
                env.close()


if __name__=="__main__":
    unittest.main()
