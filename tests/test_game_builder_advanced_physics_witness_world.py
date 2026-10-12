"""Physics-origin eyewitnesses, world consequences and independently replayed quests."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import run_advanced_session
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_physics_witness_world import (
    MAX_FOLLOWUPS,PhysicalWitnessError,
    run_physical_witness_world,verify_physical_witness_world,
)


class SignedPhysicsWitnessWorldTests(unittest.TestCase):
    @staticmethod
    def source(lane=False,settings=None,seed=1):
        scene=make_advanced_scene("racing",settings,seed=seed)
        return run_advanced_session(
            "racing",settings,("steer_right",) if lane else (),
            seed=seed,scene=scene)

    @staticmethod
    def world(settings=None,seed=0,change=None):
        source=make_advanced_scene("quest_director",settings,seed=seed)
        if change:
            layout=deepcopy(source["layout"])
            change(layout)
            return make_advanced_scene("quest_director",settings,
                                       seed=seed,layout=layout)
        return source

    @staticmethod
    def options(**options):
        return {"witnesses_required":1,"night_sight_penalty":0,
                "npc_perception":3,"witness_radius":3,
                "memory_decay_ticks":0,"event_rules":4,
                "quest_ttl":80,**options}

    @staticmethod
    def binding(source):
        return {"source_id":source["scene"]["layout"]["track_obstacle"],
                "site_id":0}

    def test_actual_original_car_collision_produces_real_direct_eyewitness(self):
        source=self.source()
        settings=self.options()
        world=self.world(settings)
        original=deepcopy(source)
        proof=run_physical_witness_world(
            source,world,quest_settings=settings,binding=self.binding(source))
        self.assertEqual(source,original)
        self.assertGreater(proof["actual_source_impacts"],0)
        self.assertIsNotNone(proof["incident"])
        self.assertTrue(proof["direct_witnesses"])
        self.assertEqual(proof["incident"]["actor"],"external:physics")
        self.assertEqual(proof["incident"]["original_source"],
                         "signed_external_physical_incident")
        self.assertEqual(proof["incident"]["site_id"],0)
        self.assertEqual(proof["incident"]["physical_source"]["source_id"],
                         source["scene"]["layout"]["track_obstacle"])
        self.assertLess(proof["world_state"]["sites"][0]["integrity"],
                        world["layout"]["sites"][0]["integrity"])
        self.assertTrue(proof["physical_origin_quest_ids"])
        self.assertTrue(verify_physical_witness_world(
            proof,source,world,quest_settings=settings))

    def test_genuine_side_lane_has_no_collision_event_or_fake_quest(self):
        source=self.source(lane=True)
        settings=self.options()
        scene=self.world(settings)
        proof=run_physical_witness_world(
            source,scene,quest_settings=settings,binding=self.binding(source))
        self.assertEqual(proof["actual_source_impacts"],0)
        self.assertIsNone(proof["incident"])
        self.assertEqual(proof["direct_witnesses"],[])
        self.assertEqual(proof["physical_origin_quest_ids"],[])
        self.assertEqual(proof["world_state"]["events_log"],[])
        self.assertTrue(verify_physical_witness_world(
            proof,source,scene,quest_settings=settings))

    def test_obstructed_npc_is_not_promoted_to_unearned_direct_witness(self):
        source=self.source()
        settings=self.options(obstacle_count=3,witness_radius=2,npc_perception=2)
        def block(layout):
            layout["obstacles"]=[9]
            layout["npcs"][0]["cell"]=10
        scene=self.world(settings,change=block)
        report=run_physical_witness_world(
            source,scene,quest_settings=settings,binding=self.binding(source))
        self.assertGreater(report["actual_source_impacts"],0)
        self.assertNotIn(0,report["direct_witnesses"])
        self.assertFalse(any(x["event_id"]==report["incident"]["id"]
                             for x in report["world_state"]["npcs"][0]["memories"]))
        self.assertTrue(verify_physical_witness_world(
            report,source,scene,quest_settings=settings))

    def test_no_unearned_player_reputation_for_external_incident(self):
        source=self.source()
        settings=self.options()
        scene=self.world(settings)
        result=run_physical_witness_world(
            source,scene,quest_settings=settings,binding=self.binding(source))
        self.assertEqual(result["world_state"]["reputation"],
                         settings.get("starting_reputation",0))
        self.assertEqual(result["world_state"]["events_log"][0]["actor"],
                         "external:physics")

    def test_real_npc_world_followups_advance_physical_time(self):
        source=self.source()
        settings=self.options()
        world=self.world(settings)
        report=run_physical_witness_world(
            source,world,quest_settings=settings,binding=self.binding(source),
            world_actions=("wait","wait:4","inspect"))
        self.assertEqual(len(report["world_timeline"]),3)
        self.assertEqual([step["action"] for step in report["world_timeline"]],
                         ["wait","wait:4","inspect"])
        self.assertGreater(report["world_state"]["tick"],4)
        self.assertEqual(report["world_state"]["turn"],4)
        self.assertTrue(verify_physical_witness_world(
            report,source,world,quest_settings=settings))

    def test_wrong_physical_object_or_site_binding_is_rejected(self):
        source=self.source()
        world=self.world(self.options())
        for binding in ({"source_id":-1,"site_id":0},
                        {"source_id":source["scene"]["layout"]["track_obstacle"],
                         "site_id":4},
                        {"site_id":0},
                        {"source_id":True,"site_id":0},
                        {"source_id":0,"site_id":False}):
            with self.subTest(binding=binding),self.assertRaises(PhysicalWitnessError):
                run_physical_witness_world(
                    source,world,quest_settings=self.options(),binding=binding)

    def test_multiple_solid_sources_are_not_attributed_by_guessing(self):
        # The current Physics receipt reports contact kinds, not fixture ID.
        # Refuse attribution to one of multiple possible authored spike sites.
        scene=make_advanced_scene("platformer",seed=1)
        source=run_advanced_session("platformer",seed=1,scene=scene)
        world=self.world(self.options())
        with self.assertRaises(PhysicalWitnessError):
            run_physical_witness_world(
                source,world,quest_settings=self.options(),
                binding={"source_id":scene["layout"]["hazards"][0],"site_id":0})

    def test_forged_incident_testimony_quest_and_reward_are_denied(self):
        source=self.source()
        settings=self.options()
        world=self.world(settings)
        good=run_physical_witness_world(
            source,world,quest_settings=settings,binding=self.binding(source))
        changes=(
            lambda p:p["incident"].update(direct_witnesses=[999]),
            lambda p:p["world_state"]["sites"][0].update(integrity=9999),
            lambda p:p["world_state"]["npcs"][0]["memories"].clear(),
            lambda p:p.update(physical_origin_quest_ids=[999]),
            lambda p:p.update(actual_source_impacts=1000),
            lambda p:p["world_state"].update(reputation=9999),
            lambda p:p.update(interop_digest="0"*64),
            lambda p:p.update(original_source_untouched=False),
        )
        for change in changes:
            forged=deepcopy(good)
            change(forged)
            with self.assertRaises(PhysicalWitnessError):
                verify_physical_witness_world(
                    forged,source,world,quest_settings=settings)

    def test_source_session_or_world_map_tampering_fails_closed(self):
        original=self.source()
        options=self.options()
        world=self.world(options)
        good=run_physical_witness_world(
            original,world,quest_settings=options,binding=self.binding(original))
        invalid=deepcopy(original)
        invalid["state"]["fuel"]=9999
        with self.assertRaises(PhysicalWitnessError):
            verify_physical_witness_world(
                good,invalid,world,quest_settings=options)
        invalid_scene=deepcopy(world)
        invalid_scene["layout"]["npcs"][0]["cell"]=48
        with self.assertRaises(PhysicalWitnessError):
            verify_physical_witness_world(
                good,original,invalid_scene,quest_settings=options)

    def test_world_actions_are_finite_and_unregistered_events_rejected(self):
        source=self.source(lane=True)
        options=self.options()
        scene=self.world(options)
        for actions in (["wait"]*(MAX_FOLLOWUPS+1),["teleport"],[42]):
            with self.assertRaises(PhysicalWitnessError):
                run_physical_witness_world(
                    source,scene,quest_settings=options,
                    binding=self.binding(source),world_actions=actions)


if __name__=="__main__":
    unittest.main()
