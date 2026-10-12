"""Durable replay-only original physics + farming/sailing/flight NPC source saves."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import unittest

from tests import test_game_builder_advanced_unified_genre_campaign as sources
from skeleton.ai.game_builder.advanced_unified_genre_save import (
    SCHEMA,MAX_SAVE_BYTES,UnifiedSaveError,
    export_unified_world_save,import_unified_world_save,
    continue_unified_world_save,
)


class TrueUnifiedSourceSaveTests(unittest.TestCase):
    @staticmethod
    def original():
        f=sources.UnifiedGenreWorldTests
        physical=f.physical()
        genre=[f.addition("farming",1)]
        world,config=f.world()
        return physical,genre,world,config

    def test_cross_genre_persistent_world_roundtrip_is_fully_independent(self):
        phys,genre,scene,cfg=self.original()
        original=(deepcopy(phys),deepcopy(genre))
        document=export_unified_world_save(phys,genre,scene,cfg)
        self.assertEqual(document["schema"],SCHEMA)
        self.assertEqual(document["physical_episode_count"],1)
        self.assertEqual(document["genre_session_count"],1)
        self.assertEqual((phys,genre),original)
        result=import_unified_world_save(document)
        self.assertTrue(result["verified"])
        self.assertEqual(result["replayed_campaign"]["digest"],
                         document["campaign_digest"])
        self.assertEqual([e["actor"] for e in
                          result["replayed_campaign"]["world_state"]["events_log"]],
                         ["external:physics","external:genre"])
        self.assertEqual(result["remaining_genre_sessions"],3)
        self.assertFalse(result["automatic_publication"])

    def test_action_continuation_replays_existing_entire_source_history(self):
        phys,genre,scene,cfg=self.original()
        saved=export_unified_world_save(phys,genre,scene,cfg)
        later=continue_unified_world_save(saved,new_world_actions=("wait","inspect"))
        confirmed=import_unified_world_save(later)
        self.assertEqual(confirmed["world_actions"],["wait","inspect"])
        self.assertEqual(confirmed["replayed_campaign"]["world_state"]["turn"],5)
        self.assertEqual(import_unified_world_save(saved)["world_actions"],[])
        self.assertNotEqual(saved["digest"],later["digest"])

    def test_second_distinct_original_genre_event_can_extend_empty_followup(self):
        f=sources.UnifiedGenreWorldTests
        phys,genre,scene,cfg=self.original()
        base=export_unified_world_save(phys,genre,scene,cfg)
        addition=f.addition("flight",2)
        newer=continue_unified_world_save(base,new_genre_sessions=(addition,))
        replay=import_unified_world_save(newer)
        self.assertEqual(replay["replayed_campaign"]["genre_session_count"],2)
        self.assertEqual(replay["replayed_campaign"]["verified_genre_event_count"],2)
        self.assertEqual(len(replay["replayed_campaign"]["world_state"]["events_log"]),3)

    def test_no_event_insertion_behind_already_completed_quest_actions(self):
        f=sources.UnifiedGenreWorldTests
        phys,genre,scene,cfg=self.original()
        old=export_unified_world_save(phys,genre,scene,cfg,world_actions=["wait"])
        with self.assertRaises(UnifiedSaveError):
            continue_unified_world_save(old,new_genre_sessions=[f.addition("flight",2)])
        self.assertEqual(import_unified_world_save(old)["world_actions"],["wait"])

    def test_outer_sha_recomputed_does_not_make_client_state_forgeries_real(self):
        phys,genre,scene,cfg=self.original()
        valid=export_unified_world_save(phys,genre,scene,cfg)
        tamperers=(
            lambda x:x["physical_episodes"][0]["source_session"]["state"]
                .update(fuel=9999),
            lambda x:x["genre_sessions"][0]["source_session"]["state"]
                .update(harvested=999),
            lambda x:x["campaign_digest"].__class__,
            lambda x:x.update(world_state_digest="0"*64),
            lambda x:x.update(head_hash="0"*64),
            lambda x:x.update(genre_event_count=99),
            lambda x:x["genre_sessions"][0]["bindings"][0].update(site_id=2),
        )
        for change in tamperers:
            modified=deepcopy(valid)
            change(modified)
            if modified==valid:continue
            stripped={k:v for k,v in modified.items() if k!="digest"}
            modified["digest"]=sha256(json.dumps(
                stripped,sort_keys=True,separators=(",",":"),
                allow_nan=False,ensure_ascii=True).encode()).hexdigest()
            with self.assertRaises(UnifiedSaveError):
                import_unified_world_save(modified)

    def test_unapproved_release_claims_unknown_fields_and_oversized_save_rejected(self):
        phys,genre,scene,cfg=self.original()
        document=export_unified_world_save(phys,genre,scene,cfg)
        for field,value in (
            ("strict_source_replay_required",False),
            ("original_game_files_modified",True),
            ("native_device_certified",True),
            ("automatic_publication_approved",True),
            ("learning_weight_promotion_approved",True),
            ("schema","other_version"),
            ("genre_session_count",True),
        ):
            bad=deepcopy(document);bad[field]=value
            with self.assertRaises(UnifiedSaveError):
                import_unified_world_save(bad)
        bad=deepcopy(document)
        bad["client_reward"]={"gold":999}
        with self.assertRaises(UnifiedSaveError):
            import_unified_world_save(bad)
        bad=deepcopy(document)
        bad["padding"]="x"*(MAX_SAVE_BYTES+1)
        with self.assertRaises(UnifiedSaveError):
            import_unified_world_save(bad)

    def test_finite_game_action_budget_and_reused_genre_proof_fail_closed(self):
        phys,genre,scene,cfg=self.original()
        base=export_unified_world_save(phys,genre,scene,cfg)
        with self.assertRaises(UnifiedSaveError):
            continue_unified_world_save(base,new_genre_sessions=genre)
        with self.assertRaises(UnifiedSaveError):
            continue_unified_world_save(base,new_world_actions=["wait"]*25)
        with self.assertRaises(UnifiedSaveError):
            continue_unified_world_save(base,new_world_actions=["teleport"])
        with self.assertRaises(UnifiedSaveError):
            continue_unified_world_save(base)
        self.assertEqual(import_unified_world_save(base)["genre_sessions"],genre)


if __name__=="__main__":
    unittest.main()
