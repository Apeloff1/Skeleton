"""Multi-genre achievements and physical incidents share one verified NPC world."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import run_advanced_session
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_unified_genre_campaign import (
    UnifiedWorldError,run_unified_game_campaign,verify_unified_game_campaign,
)
from tests.test_game_builder_advanced_genre_npc_world import TrueGenreEventToNPCWorldTests


class UnifiedGenreWorldTests(unittest.TestCase):
    @staticmethod
    def world():
        settings={"witnesses_required":1,"night_sight_penalty":0,
                  "npc_perception":3,"witness_radius":3,
                  "memory_decay_ticks":0,"event_rules":4,
                  "quest_ttl":80,"npc_autonomy":False,"npc_mobility":False}
        return make_advanced_scene("quest_director",settings,seed=0),settings

    @staticmethod
    def physical():
        scene=make_advanced_scene("racing",seed=1)
        source=run_advanced_session("racing",seed=1,scene=scene)
        return [{
            "source_session":source,"source_settings":None,
            "physics_actions":["push:east"]*8,
            "bindings":[{"source_id":scene["layout"]["track_obstacle"],
                         "site_id":0}],
            "world_actions":["wait"],
        }]

    @staticmethod
    def addition(kind="farming",site=1):
        helper=TrueGenreEventToNPCWorldTests
        source,cfg=getattr(helper,{"farming":"farm","sailing":"sailing",
                                   "flight":"flight"}[kind])()
        mapping=helper.bind(source,site)
        return {
            "source_session":source,
            "source_settings":cfg,
            "bindings":[mapping],
        }

    def test_real_physical_incident_and_harvest_share_one_persistent_world(self):
        original=self.physical()
        genre=[self.addition()]
        world,cfg=self.world()
        baseline=deepcopy(original)
        proof=run_unified_game_campaign(original,genre,world,cfg)
        self.assertEqual(original,baseline)
        self.assertEqual(proof["physical_episode_count"],1)
        self.assertEqual(proof["verified_genre_event_count"],1)
        self.assertEqual([e["actor"] for e in proof["world_state"]["events_log"]],
                         ["external:physics","external:genre"])
        self.assertEqual(proof["world_state"]["turn"],3)
        self.assertEqual([e["site_id"] for e in proof["world_state"]["events_log"]],
                         [0,1])
        self.assertTrue(any(q["origin_actor"]=="external:physics"
                            for q in proof["world_state"]["quests"]))
        self.assertTrue(verify_unified_game_campaign(
            proof,original,genre,world,cfg))

    def test_actual_maritime_cargo_adds_finite_stock_after_prior_damage(self):
        phys=self.physical()
        genre=[self.addition("sailing",1)]
        world,cfg=self.world()
        authored=deepcopy(world["layout"])
        authored["sites"][1]["stock"]=0
        world=make_advanced_scene("quest_director",cfg,seed=0,layout=authored)
        state=run_unified_game_campaign(phys,genre,world,cfg)
        self.assertEqual(state["genre_history"][0]["earned_events"][0]
                         ["real_stock_added"],1)
        self.assertEqual(state["world_state"]["sites"][1]["stock"],1)
        self.assertEqual(state["world_state"]["events_log"][0]["actor"],
                         "external:physics")
        self.assertEqual(state["world_state"]["reputation"],0)
        self.assertTrue(verify_unified_game_campaign(
            state,phys,genre,world,cfg))

    def test_three_distinct_genre_causal_events_have_true_source_chronology(self):
        phys=self.physical()
        additions=[self.addition("farming",1),
                   self.addition("sailing",2),
                   self.addition("flight",3)]
        world,cfg=self.world()
        result=run_unified_game_campaign(phys,additions,world,cfg)
        self.assertEqual(result["genre_session_count"],3)
        self.assertEqual(result["verified_genre_event_count"],3)
        self.assertEqual([record["original_editor"] for record in
                          result["genre_history"]],["farming","sailing","flight"])
        ids=[entry["world_event"]["id"] for record in result["genre_history"]
             for entry in record["earned_events"]]
        self.assertEqual(ids,[1,2,3])
        self.assertEqual(result["world_state"]["turn"],5)
        self.assertTrue(verify_unified_game_campaign(
            result,phys,additions,world,cfg))

    def test_duplicate_genre_receipt_not_allowed_to_remint_npc_quests(self):
        phys=self.physical()
        genre=self.addition()
        world,cfg=self.world()
        with self.assertRaises(UnifiedWorldError):
            run_unified_game_campaign(phys,[genre,deepcopy(genre)],world,cfg)

    def test_original_quest_world_followups_are_real_and_bounded(self):
        phys=self.physical()
        genre=[self.addition()]
        world,cfg=self.world()
        result=run_unified_game_campaign(
            phys,genre,world,cfg,world_actions=["wait","inspect"])
        self.assertEqual(result["world_state"]["turn"],5)
        self.assertEqual(len(result["world_followup_history"]),2)
        self.assertEqual(result["world_followup_history"][1]["action"],"inspect")
        self.assertTrue(verify_unified_game_campaign(
            result,phys,genre,world,cfg,world_actions=["wait","inspect"]))
        with self.assertRaises(UnifiedWorldError):
            run_unified_game_campaign(phys,genre,world,cfg,world_actions=["wait"]*25)
        with self.assertRaises(UnifiedWorldError):
            run_unified_game_campaign(phys,genre,world,cfg,world_actions=["teleport"])

    def test_source_attribution_world_memory_and_inventory_forgeries_rejected(self):
        phys=self.physical()
        genre=[self.addition()]
        world,cfg=self.world()
        proof=run_unified_game_campaign(phys,genre,world,cfg)
        cases=(
            lambda x:x["genre_history"][0]["earned_events"][0].update(
                        real_stock_added=999),
            lambda x:x["genre_history"][0]["earned_events"][0][
                      "world_event"].update(direct_witnesses=[999]),
            lambda x:x["genre_history"][0].update(head_hash="0"*64),
            lambda x:x["world_state"]["sites"][1].update(stock=999),
            lambda x:x["world_state"]["npcs"][0]["memories"].clear(),
            lambda x:x.update(verified_genre_event_count=42),
            lambda x:x.update(original_game_files_mutated=True),
        )
        for mutate in cases:
            forged=deepcopy(proof);mutate(forged)
            with self.assertRaises(UnifiedWorldError):
                verify_unified_game_campaign(forged,phys,genre,world,cfg)

    def test_changed_source_or_world_scene_cannot_transfer_achievement(self):
        phys=self.physical()
        genre=[self.addition()]
        world,cfg=self.world()
        valid=run_unified_game_campaign(phys,genre,world,cfg)
        wrong_source=deepcopy(genre)
        wrong_source[0]["source_session"]["state"]["harvested"]=999
        with self.assertRaises(UnifiedWorldError):
            run_unified_game_campaign(phys,wrong_source,world,cfg)
        new_world=make_advanced_scene("quest_director",cfg,seed=2)
        with self.assertRaises(UnifiedWorldError):
            verify_unified_game_campaign(valid,phys,genre,new_world,cfg)
        corrupted=deepcopy(phys)
        corrupted[0]["source_session"]["state"]["fuel"]=999
        with self.assertRaises(UnifiedWorldError):
            run_unified_game_campaign(corrupted,genre,world,cfg)

    def test_malformed_source_and_genre_capacity_denied(self):
        phys=self.physical()
        genre=self.addition()
        world,cfg=self.world()
        cases=[[],[{"untrusted":"reward"}],
               [{"source_session":{},"source_settings":None,"bindings":[]}],
               [genre]*5]
        for additions in cases:
            with self.subTest(additions=len(additions)),self.assertRaises(UnifiedWorldError):
                run_unified_game_campaign(phys,additions,world,cfg)


if __name__=="__main__":
    unittest.main()
