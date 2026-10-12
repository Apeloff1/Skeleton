"""Adversarial tests for actual original cross-engine NPC event ordering."""
from __future__ import annotations

from copy import deepcopy
import unittest

from tests import test_game_builder_advanced_unified_genre_campaign as fixtures
from skeleton.ai.game_builder.advanced_gameplay_runtime import run_advanced_session
from skeleton.ai.game_builder.advanced_interleaved_world import (
    InterleavedWorldError,run_interleaved_world,verify_interleaved_world,
)


class OriginalInterleavedWorldTests(unittest.TestCase):
    @staticmethod
    def inputs(*,genre="farming"):
        f=fixtures.UnifiedGenreWorldTests
        physical=deepcopy(f.physical())
        physical[0]["world_actions"]=[]
        genres=[f.addition(genre,site=1)]
        scene,cfg=f.world()
        return physical,genres,scene,cfg

    @staticmethod
    def timeline(*lanes):
        return [
            ({"at":index,"lane":"world","action":"wait"} if name=="world"
             else {"at":index,"lane":name,"source_index":0,"event_index":0})
            for index,name in enumerate(lanes)
        ]

    def test_true_interleaving_changes_single_world_not_decorative_order(self):
        physical,genres,scene,cfg=self.inputs()
        inputs=deepcopy((physical,genres))
        ordered=self.timeline("genre","world","physical","world")
        proof=run_interleaved_world(physical,genres,scene,ordered,cfg)
        self.assertEqual((physical,genres),inputs)
        self.assertEqual(proof["authentic_physical_event_count"],1)
        self.assertEqual(proof["authentic_genre_event_count"],1)
        self.assertEqual(proof["scheduled_world_actions"],2)
        self.assertEqual(proof["world_state"]["turn"],4)
        self.assertEqual(proof["world_state"]["tick"],4)
        self.assertEqual([x["actor"] for x in proof["world_state"]["events_log"]],
                         ["external:genre","external:physics"])
        self.assertEqual([x["lane"] for x in proof["timeline"]],
                         ["genre","world","physical","world"])
        self.assertEqual([x["world_tick"] for x in proof["timeline"]],[1,2,3,4])
        self.assertTrue(verify_interleaved_world(
            proof,physical,genres,scene,ordered,cfg))

    def test_authored_interleaving_changes_real_quest_source_ids_and_digests(self):
        physical,genres,scene,cfg=self.inputs()
        early=self.timeline("genre","physical")
        late=self.timeline("physical","genre")
        a=run_interleaved_world(physical,genres,scene,early,cfg)
        b=run_interleaved_world(physical,genres,scene,late,cfg)
        self.assertNotEqual(a["digest"],b["digest"])
        self.assertEqual([x["actor"] for x in a["world_state"]["events_log"]],
                         ["external:genre","external:physics"])
        self.assertEqual([x["actor"] for x in b["world_state"]["events_log"]],
                         ["external:physics","external:genre"])
        self.assertEqual(a["world_state"]["turn"],b["world_state"]["turn"])
        self.assertEqual(a["world_state"]["reputation"],0)
        self.assertTrue(verify_interleaved_world(
            a,physical,genres,scene,early,cfg))

    def test_real_maritime_cargo_can_precede_original_collision_without_free_gold(self):
        physical,genres,scene,cfg=self.inputs(genre="sailing")
        chart=deepcopy(scene["layout"])
        chart["sites"][1]["stock"]=0
        from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
        scene=make_advanced_scene("quest_director",cfg,seed=0,layout=chart)
        schedule=self.timeline("genre","physical","world")
        result=run_interleaved_world(physical,genres,scene,schedule,cfg)
        self.assertEqual(result["world_state"]["sites"][1]["stock"],1)
        self.assertEqual(result["world_state"]["reputation"],0)
        self.assertEqual(result["timeline"][0]["source"]["real_stock"],1)
        self.assertEqual(result["timeline"][0]["source"]["verified_event"],
                         "original_cargo_delivered")
        self.assertTrue(verify_interleaved_world(
            result,physical,genres,scene,schedule,cfg))

    def test_aircraft_landing_and_physically_hit_site_preserve_true_witnesses(self):
        physical,genres,scene,cfg=self.inputs(genre="flight")
        schedule=self.timeline("physical","world","genre")
        record=run_interleaved_world(physical,genres,scene,schedule,cfg)
        self.assertEqual(record["timeline"][2]["source"]["verified_event"],
                         "runway_landing_confirmed")
        self.assertGreater(len(record["timeline"][0]["source"]["direct_witnesses"]),0)
        self.assertGreater(len(record["timeline"][2]["source"]["direct_witnesses"]),0)
        self.assertEqual([q["origin_actor"] for q in record["world_state"]["quests"]],
                         ["external:physics","external:genre"])

    def test_scheduler_rejects_missing_extra_and_duplicate_real_source_event(self):
        physical,genres,scene,cfg=self.inputs()
        for bad in (
            self.timeline("genre"),
            self.timeline("physical"),
            self.timeline("physical","genre","genre"),
            self.timeline("physical","physical","genre"),
        ):
            with self.subTest(bad=bad),self.assertRaises(InterleavedWorldError):
                run_interleaved_world(physical,genres,scene,bad,cfg)

    def test_scheduler_denies_fabricated_clock_gaps_backdating_and_wrong_index(self):
        physical,genres,scene,cfg=self.inputs()
        correct=self.timeline("physical","genre")
        for change in (
            lambda x:x[0].update(at=1),
            lambda x:x[1].update(at=0),
            lambda x:x[1].update(at=2),
            lambda x:x[0].update(source_index=99),
            lambda x:x[1].update(event_index=-1),
            lambda x:x[1].update(event_index=True),
            lambda x:x[0].update(lane="admin_reward"),
            lambda x:x[0].update(action="mint_gold"),
        ):
            wrong=deepcopy(correct);change(wrong)
            with self.assertRaises(InterleavedWorldError):
                run_interleaved_world(physical,genres,scene,wrong,cfg)

    def test_only_actual_world_actions_may_advance_shared_npc_clock(self):
        physical,genres,scene,cfg=self.inputs()
        actions=self.timeline("physical","world","world","genre")
        record=run_interleaved_world(physical,genres,scene,actions,cfg)
        self.assertEqual(record["world_state"]["turn"],4)
        self.assertEqual(record["scheduled_world_actions"],2)
        self.assertTrue(verify_interleaved_world(
            record,physical,genres,scene,actions,cfg))
        bad=deepcopy(actions)
        bad[1]["action"]="teleport"
        with self.assertRaises(InterleavedWorldError):
            run_interleaved_world(physical,genres,scene,bad,cfg)

    def test_source_action_tampering_and_world_reward_forgery_fail_replay(self):
        physical,genres,scene,cfg=self.inputs()
        schedule=self.timeline("genre","physical")
        good=run_interleaved_world(physical,genres,scene,schedule,cfg)
        edits=(
            lambda x:x["world_state"]["sites"][1].update(stock=999),
            lambda x:x["world_state"]["npcs"][0]["memories"].clear(),
            lambda x:x["timeline"][0]["source"].update(real_stock=500),
            lambda x:x["timeline"][1]["source"].update(source_id=999),
            lambda x:x["timeline"][0].update(head_hash="0"*64),
            lambda x:x.update(free_rewards_granted=True),
            lambda x:x.update(authentic_genre_event_count=42),
        )
        for modify in edits:
            forged=deepcopy(good);modify(forged)
            with self.assertRaises(InterleavedWorldError):
                verify_interleaved_world(forged,physical,genres,scene,schedule,cfg)
        mutated=deepcopy(genres)
        mutated[0]["source_session"]["state"]["harvested"]=999
        with self.assertRaises(InterleavedWorldError):
            run_interleaved_world(physical,mutated,scene,schedule,cfg)

    def test_scheduled_world_actions_cannot_be_hidden_in_input_physics_episode(self):
        physical,genres,scene,cfg=self.inputs()
        physical[0]["world_actions"]=["wait"]
        with self.assertRaises(InterleavedWorldError):
            run_interleaved_world(
                physical,genres,scene,self.timeline("physical","genre"),cfg)

    def test_typed_world_entries_reject_extra_client_fields_and_impossible_lanes(self):
        physical,genres,scene,cfg=self.inputs()
        schedule=self.timeline("physical","genre")
        invalid=(
            lambda x:x[0].update(user_reward=999),
            lambda x:x[0].update(at=True),
            lambda x:x[1].update(source_index="0"),
            lambda x:x[1].update(lane=[]),
            lambda x:x[0].pop("at"),
        )
        for alter in invalid:
            wrong=deepcopy(schedule);alter(wrong)
            with self.assertRaises(InterleavedWorldError):
                run_interleaved_world(physical,genres,scene,wrong,cfg)


if __name__=="__main__":
    unittest.main()
