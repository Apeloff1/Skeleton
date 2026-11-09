"""Adversarial original NPC dialogue evidence and independent source replay."""
from __future__ import annotations
from copy import deepcopy
import unittest
from skeleton.ai.game_builder.system_editors import make_editor_document,catalog,SystemEditorError
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES,run_advanced_session,verify_advanced_session,AdvancedRuntimeError)
from skeleton.ai.game_builder.advanced_level_scenes import (
    make_advanced_scene,validate_advanced_scene,SceneError)
from skeleton.ai.game_builder.advanced_gameplay_save import (
    export_advanced_savegame,import_advanced_savegame,continue_advanced_savegame)
from skeleton.ai.game_builder.system_editor_assembly import compile_system_assembly

class OriginalDialogueGameTests(unittest.TestCase):
    EVIDENCE=("approach:0","empathize","ask:bridge","listen","record",
              "approach:1","empathize","ask:bridge","listen","record",
              "verify:bridge","report")

    def test_advanced_playable_maturity(self):
        self.assertIn("dialogue",ENGINES)
        spec=next(s for s in catalog() if s["id"]=="dialogue")
        self.assertEqual(spec["runtime_maturity"],"advanced_reference_runtime")
        self.assertEqual(spec["progression_floor"],"advanced")
        self.assertGreaterEqual(len(spec["fields"]),17)

    def test_source_independent_npc_quest_nonterminal(self):
        s=run_advanced_session("dialogue",actions=self.EVIDENCE+("wait",))
        self.assertTrue(verify_advanced_session(s))
        self.assertTrue(s["state"]["checkpoint"])
        self.assertFalse(s["terminal"])
        self.assertEqual(s["state"]["verified_topics"],["bridge"])
        self.assertEqual(len(s["state"]["records"]),2)
        self.assertEqual(s["state"]["reputation"],2)
        self.assertFalse(s["native_hardware_verified"])

    def test_illegal_unearned_speech_cannot_create_evidence(self):
        for actions in (("record",),("report",),("verify:bridge",),
                        ("approach:0","listen"),
                        ("approach:0","ask:bridge","listen"),
                        ("approach:0","empathize","ask:harvest","listen"),
                        ("approach:0","empathize","ask:bridge","listen","record","record"),
                        ("approach:7",)):
            with self.subTest(actions=actions),self.assertRaises(AdvancedRuntimeError):
                run_advanced_session("dialogue",{"speakers":4},actions=actions)
        with self.assertRaises(SystemEditorError):
            make_editor_document("dialogue",{"min_witnesses":0})

    def test_exact_authored_scene_and_save_replay(self):
        scene=make_advanced_scene("dialogue",seed=3)
        self.assertEqual(validate_advanced_scene(scene),scene)
        s=run_advanced_session("dialogue",seed=3,scene=scene,actions=self.EVIDENCE)
        self.assertTrue(verify_advanced_session(s))
        save=export_advanced_savegame(s)
        self.assertTrue(import_advanced_savegame(save)["verified"])
        next_save=continue_advanced_savegame(save,["leave","rest"])
        self.assertTrue(import_advanced_savegame(next_save)["verified"])
        tampered=deepcopy(s)
        tampered["state"]["verified_topics"].append("harvest")
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(tampered)
        for attack in ("speaker","topic","extra","markup"):
            bad=deepcopy(scene["layout"])
            if attack=="speaker":bad["statements"][0]["speaker"]=8
            elif attack=="topic":bad["statements"][0]["topic"]="foreign_source"
            elif attack=="extra":bad["unexpected"]=True
            else:bad["statements"][0]["claim"]="<script>alert(1)</script>"
            with self.subTest(attack=attack),self.assertRaises(SceneError):
                make_advanced_scene("dialogue",layout=bad)

    def test_memory_budget_and_finite_assistance(self):
        s=run_advanced_session("dialogue",{"memory_turns":0,"gift_tokens":1},
              actions=("approach:0","offer:aid","ask:bridge","listen"))
        self.assertEqual(s["state"]["memory"],[])
        self.assertEqual(s["state"]["favors"],0)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("dialogue",{"gift_tokens":1},
               actions=("approach:0","offer:aid","offer:aid"))

    def test_assembly_includes_source_verified_gameplay(self):
        scene=make_advanced_scene("dialogue",seed=4)
        assembly=compile_system_assembly(
           "original_social_studio",[make_editor_document("dialogue")],
           authorized=True,scenes=[scene])
        self.assertEqual(assembly["authored_scene_count"],1)
        self.assertEqual(assembly["advanced_runtime_evidence"][0]["editor"],"dialogue")
        self.assertFalse(assembly["ready_for_release"])

if __name__=="__main__":
    unittest.main()
