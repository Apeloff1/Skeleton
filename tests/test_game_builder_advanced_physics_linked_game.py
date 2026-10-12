"""Actual source-progression and physics-coupled health, repair and replay tests."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_physics_linked_game import (
    SCHEMA,MAX_TURNS,LinkedPhysicsError,run_linked_physics_game,
    verify_linked_physics_game,
)


class LinkedProgressionTests(unittest.TestCase):
    @staticmethod
    def scene(editor,settings=None,seed=1):
        return make_advanced_scene(editor,settings,seed=seed)

    @staticmethod
    def move(action,physical=("push:east",)*8,ability="none"):
        return {"source_action":action,
                "physical_actions":list(physical),"ability":ability}

    def test_real_platformer_loss_reduces_coupled_gameplay_health(self):
        scene=self.scene("platformer")
        move=self.move("wait")
        report=run_linked_physics_game("platformer",scene,turns=[move])
        self.assertEqual(report["schema"],SCHEMA)
        self.assertGreater(report["linked_state"]["physical_impacts"],0)
        self.assertLess(report["linked_state"]["vital"],5)
        self.assertEqual(report["source_state"]["health"],5)
        self.assertTrue(verify_linked_physics_game(report,scene))

    def test_actual_physical_defeat_is_terminal_even_if_platformer_isnt(self):
        scene=self.scene("platformer")
        strike=self.move("wait")
        turns=[strike,strike,strike]
        report=run_linked_physics_game("platformer",scene,turns=turns)
        self.assertEqual(report["linked_state"]["vital"],0)
        self.assertEqual(report["linked_state"]["game_status"],"defeat")
        self.assertTrue(report["linked_state"]["terminal"])
        self.assertFalse(report["source_state"]["terminal"] if "terminal" in report["source_state"] else False)
        with self.assertRaises(LinkedPhysicsError):
            run_linked_physics_game("platformer",scene,turns=turns+[strike])

    def test_finite_brace_mitigates_real_contact_not_artificial_win(self):
        scene=self.scene("racing",{"track_length":80,"laps":2})
        hit=self.move("coast")
        braced=self.move("coast",ability="brace")
        raw=run_linked_physics_game("racing",scene,{"track_length":80,"laps":2},[hit])
        protected=run_linked_physics_game("racing",scene,{"track_length":80,"laps":2},[braced])
        self.assertGreater(protected["linked_state"]["vital"],raw["linked_state"]["vital"])
        self.assertEqual(protected["linked_state"]["brace_charges"],1)
        self.assertFalse(protected["linked_state"]["terminal"])
        self.assertTrue(verify_linked_physics_game(protected,scene,{"track_length":80,"laps":2}))

    def test_verified_lane_change_avoids_real_physical_damage(self):
        settings={"track_length":80,"laps":2}
        scene=self.scene("racing",settings,seed=2)
        moved=self.move("steer_right")
        report=run_linked_physics_game("racing",scene,settings,[moved])
        self.assertEqual(report["linked_state"]["physical_impacts"],0)
        self.assertEqual(report["linked_state"]["damage_taken"],0)
        self.assertEqual(report["source_state"]["lane"],1)
        self.assertTrue(verify_linked_physics_game(report,scene,settings))

    def test_repair_is_finite_and_requires_no_incoming_impact(self):
        scene=self.scene("platformer")
        turns=[self.move("wait"),self.move("wait",("inspect",),ability="repair")]
        report=run_linked_physics_game("platformer",scene,turns=turns)
        self.assertGreater(report["linked_state"]["recovered"],0)
        self.assertEqual(report["linked_state"]["repair_kits"],1)
        self.assertEqual(report["turns"][1]["contact_count"],0)
        self.assertTrue(verify_linked_physics_game(report,scene))

    def test_original_world_terrain_impacts_linked_structure_durability(self):
        scene=self.scene("sandbox",seed=3)
        before=run_advanced_session("sandbox",seed=3,scene=scene)
        result=run_linked_physics_game(
            "sandbox",scene,turns=[self.move("tick")])
        self.assertLess(result["linked_state"]["vital"],100)
        self.assertGreater(result["linked_state"]["physical_impacts"],0)
        self.assertEqual(before["state"]["region"],
                         result["source_state"]["region"])
        self.assertTrue(verify_advanced_session(before))
        self.assertTrue(verify_linked_physics_game(result,scene))

    def test_source_progression_actually_advances_canonical_game(self):
        scene=self.scene("racing",{"track_length":80,"laps":2})
        turns=[self.move("accelerate",("inspect",)),
               self.move("accelerate",("inspect",))]
        report=run_linked_physics_game("racing",scene,{"track_length":80,"laps":2},turns)
        real=run_advanced_session("racing",{"track_length":80,"laps":2},
                                  ("accelerate","accelerate"),seed=1,scene=scene)
        self.assertEqual(report["source_state"],real["state"])
        self.assertGreater(real["state"]["distance"],0)
        self.assertEqual(report["linked_state"]["physical_impacts"],0)

    def test_hash_chain_resists_all_client_side_vital_or_collision_forgery(self):
        scene=self.scene("platformer")
        report=run_linked_physics_game("platformer",scene,turns=[self.move("wait")])
        for key,value in (("vital",99),("damage_taken",0),
                          ("game_status","victory"),("repair_kits",99)):
            forged=deepcopy(report);forged["linked_state"][key]=value
            with self.assertRaises(LinkedPhysicsError):
                verify_linked_physics_game(forged,scene)
        forged=deepcopy(report);forged["turns"][0]["contact_count"]=99
        with self.assertRaises(LinkedPhysicsError):
            verify_linked_physics_game(forged,scene)
        forged=deepcopy(report);forged["turns"][0]["head_hash"]="0"*64
        with self.assertRaises(LinkedPhysicsError):
            verify_linked_physics_game(forged,scene)

    def test_reject_unreviewed_source_actions_resource_cheats_and_postmortem(self):
        scene=self.scene("platformer")
        for turns in (
            [{"source_action":"teleport","physical_actions":["inspect"],"ability":"none"}],
            [self.move("wait",ability="cheat")],
            [self.move("wait",("spawn:gold",))],
            [self.move("wait",("inspect",),ability="brace")]*3,
            [self.move("wait")]*25,
            [{"source_action":"wait","physical_actions":["inspect"],"ability":"none",
              "vital":9999}],
        ):
            with self.subTest(turns=turns):
                with self.assertRaises(LinkedPhysicsError):
                    run_linked_physics_game("platformer",scene,turns=turns)
        self.assertEqual(MAX_TURNS,24)

    def test_cannot_splice_scene_or_settings_identity_into_campaign(self):
        scene=self.scene("platformer",seed=2)
        campaign=run_linked_physics_game("platformer",scene,
                                          turns=[self.move("wait")])
        changed=self.scene("platformer",seed=3)
        with self.assertRaises(LinkedPhysicsError):
            verify_linked_physics_game(campaign,changed)
        forged=deepcopy(campaign);forged["source_gameplay_digest"]="0"*64
        with self.assertRaises(LinkedPhysicsError):
            verify_linked_physics_game(forged,scene)


if __name__=="__main__":
    unittest.main()
