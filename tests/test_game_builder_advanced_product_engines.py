"""Executable original production subsystems: recorded effects and checked replay."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES, AdvancedRuntimeError, run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    make_advanced_scene, validate_advanced_scene, SceneError,
)
from skeleton.jeeves.game_studio_environment import (
    make_studio_source, StudioGameEnvironment,
)


class ExecutableSubsystems(unittest.TestCase):
    def test_networking_real_tick_delivery_and_bounded_authority(self):
        self.assertIn("networking", ENGINES)
        doc=run_advanced_session("networking",{"max_players":3,"rollback_frames":8},
            ["join:1","send:1:right","tick:4","sync","retire"],seed=2)
        self.assertTrue(doc["state"]["finished"])
        self.assertEqual(doc["state"]["delivered"],1)
        self.assertTrue(doc["state"]["acks"])
        self.assertTrue(verify_advanced_session(doc,{"max_players":3,"rollback_frames":8}))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("networking",{"max_players":1},["join:1"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("networking",actions=["send:1:left"])

    def test_save_system_actual_restore_migration_and_history(self):
        cfg={"save_slots":3,"history_depth":2}
        doc=run_advanced_session("save_system",cfg,
            ["save:0","advance:10","damage","migrate","load:0","verify","retire"],seed=7)
        s=doc["state"]
        self.assertTrue(s["finished"])
        self.assertEqual(s["saved"],1)
        self.assertEqual(s["loaded"],1)
        self.assertEqual(s["migrations"],2)
        self.assertEqual(s["position"],7)
        self.assertTrue(verify_advanced_session(doc,cfg))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("save_system",actions=["load:0"])

    def test_animation_blend_clip_events_and_root_motion(self):
        cfg={"states":4,"blend_ticks":2,"root_motion":True}
        doc=run_advanced_session("animation",cfg,[
            "play:walk","tick:4","tick:16","event","finish"],seed=0)
        self.assertEqual(doc["state"]["current"],"walk")
        self.assertGreaterEqual(doc["state"]["transitions"],1)
        self.assertGreater(doc["state"]["root_position"],0)
        self.assertTrue(doc["state"]["finished"])
        self.assertTrue(verify_advanced_session(doc,cfg))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("animation",cfg,["play:run"])

    def test_audio_real_channel_budget_and_sample_clock(self):
        cfg={"channels":1,"dynamic_layers":4,"mix_strategy":"priority"}
        doc=run_advanced_session("audio",cfg,[
            "play:0","play:1","far","mix","tick:4096","tick:4096","tick:4096","tick:4096","tick:4096","finish"],seed=0)
        self.assertTrue(doc["state"]["finished"])
        self.assertEqual(doc["state"]["stolen"],1)
        self.assertEqual(doc["state"]["completed"],1)
        self.assertTrue(verify_advanced_session(doc,cfg))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("audio",{"channels":1,"mix_strategy":"fixed"},
                                 ["play:0","play:1"])

    def test_all_four_own_authored_scenes_and_emulator_protocol(self):
        for editor in ("networking","save_system","animation","audio"):
            with self.subTest(editor=editor):
                scene=make_advanced_scene(editor,seed=13)
                receipt=run_advanced_session(editor,actions=["inspect"],seed=13,scene=scene)
                self.assertTrue(verify_advanced_session(receipt))
                source=make_studio_source(editor,actions=("inspect",))
                env=StudioGameEnvironment(source,max_steps=4)
                env.reset(2**40)
                env.step("inspect")
                saved=env.snapshot()
                clone=StudioGameEnvironment(source,max_steps=4)
                clone.restore(saved)
                self.assertEqual(clone.snapshot(),saved)
                tampered=deepcopy(scene)
                tampered["layout"]["title"]="changed"
                with self.assertRaises(SceneError):
                    validate_advanced_scene(tampered)
                env.close()


if __name__=="__main__":
    unittest.main()
