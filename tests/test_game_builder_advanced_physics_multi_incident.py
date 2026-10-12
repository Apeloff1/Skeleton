"""Adversarial multi-object physical world quests with real source chronology."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import run_advanced_session
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_physics_interop import rehearse_physics_encounter
from skeleton.ai.game_builder.advanced_physics_multi_incident_world import (
    MAX_OBJECTS,MAX_FOLLOWUPS,MultiIncidentError,
    run_multi_incident_world,verify_multi_incident_world,
)


class ActualMultiIncidentNPCTests(unittest.TestCase):
    @staticmethod
    def world():
        rules={"witnesses_required":1,"night_sight_penalty":0,
               "npc_perception":3,"witness_radius":3,"memory_decay_ticks":0,
               "event_rules":4,"quest_ttl":80}
        return rules,make_advanced_scene("quest_director",rules,seed=0)

    @staticmethod
    def original(editor="racing",actions=(),seed=1):
        scene=make_advanced_scene(editor,seed=seed)
        return run_advanced_session(editor,actions=actions,seed=seed,scene=scene)

    def test_real_original_collision_produces_one_grounded_source_incident(self):
        source=self.original()
        rules,world=self.world()
        obj=source["scene"]["layout"]["track_obstacle"]
        before=deepcopy(source)
        result=run_multi_incident_world(
            source,world,quest_settings=rules,
            bindings=[{"source_id":obj,"site_id":0}])
        self.assertEqual(source,before)
        self.assertEqual(len(result["incidents"]),1)
        event=result["incidents"][0]
        self.assertGreater(event["real_contact_count"],0)
        self.assertEqual(event["source_id"],obj)
        self.assertEqual(event["incident"]["actor"],"external:physics")
        self.assertTrue(event["direct_witnesses"])
        self.assertTrue(event["quest_ids"])
        self.assertEqual(result["world_state"]["reputation"],0)
        self.assertTrue(verify_multi_incident_world(
            result,source,world,quest_settings=rules))

    def test_original_lane_avoidance_creates_no_incident_or_fake_quest(self):
        source=self.original(actions=("steer_right",))
        rules,world=self.world()
        obj=source["scene"]["layout"]["track_obstacle"]
        result=run_multi_incident_world(
            source,world,quest_settings=rules,
            bindings=[{"source_id":obj,"site_id":0}])
        self.assertEqual(result["incidents"],[])
        self.assertEqual(result["world_state"]["events_log"],[])
        self.assertEqual(result["world_state"]["quests"],[])
        self.assertTrue(verify_multi_incident_world(
            result,source,world,quest_settings=rules))

    def test_multiple_original_hazards_only_hit_object_can_mint_incident(self):
        source=self.original(editor="platformer")
        proof=rehearse_physics_encounter(source)
        self.assertGreaterEqual(len(proof["witnesses"]),2)
        rules,world=self.world()
        hit={h["source_id"] for h in proof["source_fixture_impacts"]}
        candidates=proof["witnesses"]
        mappings=[{"source_id":w["source_id"],"site_id":i}
                  for i,w in enumerate(candidates[:4])]
        result=run_multi_incident_world(
            source,world,quest_settings=rules,bindings=mappings)
        actual={e["source_id"] for e in result["incidents"]}
        self.assertEqual(actual,hit&{m["source_id"] for m in mappings})
        self.assertEqual(len(result["world_state"]["events_log"]),len(actual))
        self.assertTrue(all(e["real_contact_count"]>0 for e in result["incidents"]))
        self.assertTrue(verify_multi_incident_world(
            result,source,world,quest_settings=rules))

    def test_event_order_has_source_timestamps_not_client_order(self):
        source=self.original(editor="platformer",seed=4)
        rules,world=self.world()
        candidates=rehearse_physics_encounter(source)["witnesses"][:4]
        mappings=[{"source_id":w["source_id"],"site_id":i}
                  for i,w in enumerate(candidates)]
        backward=list(reversed(mappings))
        result=run_multi_incident_world(
            source,world,quest_settings=rules,bindings=backward)
        times=[(x["physics_first_tick"],x["physics_first_frame"],
                x["fixture_index"]) for x in result["incidents"]]
        self.assertEqual(times,sorted(times))
        self.assertEqual([x["world_turn"] for x in result["incidents"]],
                         list(range(1,len(times)+1)))
        self.assertTrue(verify_multi_incident_world(
            result,source,world,quest_settings=rules))

    def test_real_world_followups_share_single_persistent_npc_state(self):
        source=self.original()
        rules,world=self.world()
        result=run_multi_incident_world(
            source,world,quest_settings=rules,
            bindings=[{"source_id":source["scene"]["layout"]["track_obstacle"],
                       "site_id":0}],
            world_actions=["wait","wait:4","inspect"])
        self.assertEqual([e["action"] for e in result["world_timeline"]],
                         ["wait","wait:4","inspect"])
        self.assertEqual(result["world_state"]["turn"],4)
        self.assertGreater(result["world_state"]["tick"],4)
        self.assertTrue(verify_multi_incident_world(
            result,source,world,quest_settings=rules))

    def test_bad_source_to_world_mapping_is_rejected_not_guessed(self):
        source=self.original()
        _,world=self.world()
        obj=source["scene"]["layout"]["track_obstacle"]
        wrong=(
            [],[{"source_id":obj,"site_id":0}]*2,
            [{"source_id":obj,"site_id":0},{"source_id":42,"site_id":0}],
            [{"source_id":-1,"site_id":0}],
            [{"source_id":True,"site_id":0}],
            [{"source_id":obj,"site_id":4}],
            [{"source_id":987654,"site_id":0}],
            [{"source_id":obj,"site_id":0}]* (MAX_OBJECTS+1),
        )
        for bindings in wrong:
            with self.subTest(bindings=bindings),self.assertRaises(MultiIncidentError):
                run_multi_incident_world(source,world,bindings=bindings)

    def test_finite_followup_and_disallowed_commands_are_enforced(self):
        source=self.original()
        _,world=self.world()
        mapping=[{"source_id":source["scene"]["layout"]["track_obstacle"],
                  "site_id":0}]
        for actions in (["wait"]*(MAX_FOLLOWUPS+1),["teleport"],["wait",None]):
            with self.assertRaises(MultiIncidentError):
                run_multi_incident_world(source,world,bindings=mapping,world_actions=actions)

    def test_tampered_world_quest_testimony_physics_order_and_receipt_denied(self):
        source=self.original()
        rules,world=self.world()
        good=run_multi_incident_world(
            source,world,quest_settings=rules,
            bindings=[{"source_id":source["scene"]["layout"]["track_obstacle"],
                       "site_id":0}])
        variants=(
            lambda x:x["incidents"][0].update(real_contact_count=999),
            lambda x:x["incidents"][0].update(physics_first_frame=999),
            lambda x:x["incidents"][0]["incident"].update(direct_witnesses=[999]),
            lambda x:x["world_state"]["npcs"][0]["memories"].clear(),
            lambda x:x["world_state"]["sites"][0].update(integrity=999),
            lambda x:x.update(physics_session_digest="0"*64),
            lambda x:x.update(source_game_unchanged=False),
        )
        for mutate in variants:
            forged=deepcopy(good)
            mutate(forged)
            with self.assertRaises(MultiIncidentError):
                verify_multi_incident_world(forged,source,world,quest_settings=rules)

    def test_original_session_and_world_map_cannot_be_substituted(self):
        source=self.original()
        rules,world=self.world()
        receipt=run_multi_incident_world(
            source,world,quest_settings=rules,
            bindings=[{"source_id":source["scene"]["layout"]["track_obstacle"],
                       "site_id":0}])
        forged=deepcopy(source)
        forged["state"]["fuel"]=9999
        with self.assertRaises(MultiIncidentError):
            verify_multi_incident_world(receipt,forged,world,quest_settings=rules)
        revised=make_advanced_scene("quest_director",rules,seed=2)
        with self.assertRaises(MultiIncidentError):
            verify_multi_incident_world(receipt,source,revised,quest_settings=rules)


if __name__=="__main__":
    unittest.main()
