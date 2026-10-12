"""Replay-only portable original game event-clock source input logs."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import unittest

from tests import test_game_builder_advanced_interleaved_world as clock_fixtures
from tests import test_game_builder_advanced_unified_genre_campaign as genre_fixtures
from skeleton.ai.game_builder.advanced_interleaved_save import (
    SCHEMA,MAX_SAVE_BYTES,InterleavedSaveError,
    export_interleaved_save,import_interleaved_save,
    continue_interleaved_save,
)


class OriginalInterleavedSaveTests(unittest.TestCase):
    @staticmethod
    def source():
        physical,genres,world,cfg=clock_fixtures.OriginalInterleavedWorldTests.inputs()
        timeline=clock_fixtures.OriginalInterleavedWorldTests.timeline(
            "genre","physical")
        return physical,genres,world,cfg,timeline

    def test_exact_world_clock_roundtrip_keeps_real_eyewitness_and_gameplay(self):
        p,g,s,c,t=self.source()
        original=deepcopy((p,g,s,c,t))
        saved=export_interleaved_save(p,g,s,t,c)
        self.assertEqual(saved["schema"],SCHEMA)
        restored=import_interleaved_save(saved)
        self.assertTrue(restored["verified"])
        self.assertEqual(restored["replayed_world"]["digest"],saved["campaign_digest"])
        self.assertEqual(restored["replayed_world"]["world_state"]["turn"],2)
        self.assertEqual([e["actor"] for e in
                          restored["replayed_world"]["world_state"]["events_log"]],
                         ["external:genre","external:physics"])
        self.assertEqual((p,g,s,c,t),original)
        self.assertFalse(restored["source_projects_mutated"])

    def test_append_actual_npc_wait_does_not_rewrite_previous_source_event_ids(self):
        p,g,s,c,t=self.source()
        old=export_interleaved_save(p,g,s,t,c)
        amended=continue_interleaved_save(old,additional_timeline=[
            {"at":2,"lane":"world","action":"wait"},
            {"at":3,"lane":"world","action":"inspect"},
        ])
        actual=import_interleaved_save(amended)
        self.assertEqual(actual["replayed_world"]["world_state"]["turn"],4)
        self.assertEqual(actual["replayed_world"]["scheduled_world_actions"],2)
        self.assertEqual(actual["replayed_world"]["timeline"][:2],
                         import_interleaved_save(old)["replayed_world"]["timeline"][:2])
        self.assertEqual(import_interleaved_save(old)["world_scene"],s)

    def test_later_original_sailing_source_adds_earned_event_after_physics_and_farm(self):
        p,g,s,c,t=self.source()
        initial=export_interleaved_save(p,g,s,t,c)
        ship=genre_fixtures.UnifiedGenreWorldTests.addition("sailing",2)
        final=continue_interleaved_save(
            initial,additional_genre=[ship],
            additional_timeline=[{"at":2,"lane":"genre",
                                  "source_index":1,"event_index":0}])
        reread=import_interleaved_save(final)
        self.assertEqual(reread["replayed_world"]["authentic_genre_event_count"],2)
        self.assertEqual(reread["replayed_world"]["world_state"]["turn"],3)
        self.assertEqual(reread["replayed_world"]["timeline"][2]
                         ["source"]["verified_event"],"original_cargo_delivered")

    def test_saved_world_time_cannot_be_retroactively_edited_by_new_event(self):
        p,g,s,c,t=self.source()
        saved=export_interleaved_save(p,g,s,t,c)
        for suffix in (
            [{"at":0,"lane":"world","action":"wait"}],
            [{"at":5,"lane":"world","action":"wait"}],
            [{"at":2,"lane":"world","action":"teleport"}],
        ):
            with self.subTest(suffix=suffix),self.assertRaises(InterleavedSaveError):
                continue_interleaved_save(saved,additional_timeline=suffix)

    def test_full_replay_rejects_attacker_recomputed_outer_sha_on_source_forgery(self):
        p,g,s,c,t=self.source()
        good=export_interleaved_save(p,g,s,t,c)
        changes=(
            lambda x:x["physical_episodes"][0]["source_session"]["state"].update(fuel=999),
            lambda x:x["genre_sessions"][0]["source_session"]["state"].update(harvested=999),
            lambda x:x["world_scene"].update(seed=2),
            lambda x:x.update(campaign_digest="0"*64),
            lambda x:x.update(actual_world_state_digest="0"*64),
            lambda x:x["timeline"][0].update(lane="world",action="mint_gold"),
            lambda x:x.update(world_tick=999),
        )
        for mutate in changes:
            forged=deepcopy(good);mutate(forged)
            data={k:v for k,v in forged.items() if k!="digest"}
            forged["digest"]=hashlib.sha256(json.dumps(
                data,sort_keys=True,separators=(",",":"),
                ensure_ascii=True,allow_nan=False).encode()).hexdigest()
            with self.assertRaises(InterleavedSaveError):
                import_interleaved_save(forged)

    def test_false_certification_and_schema_additions_do_not_grant_device_release(self):
        p,g,s,c,t=self.source()
        good=export_interleaved_save(p,g,s,t,c)
        for field,value in (
            ("native_all_genres_certified",True),
            ("automatic_ai_weights_promotion",True),
            ("original_project_files_mutated",True),
            ("automatic_publication_approved",True),
            ("replay_required",False),
            ("schema","untrusted"),
            ("physical_source_count",True),
        ):
            forged=deepcopy(good);forged[field]=value
            with self.assertRaises(InterleavedSaveError):
                import_interleaved_save(forged)
        forged=deepcopy(good);forged["client_gold"]=999
        with self.assertRaises(InterleavedSaveError):
            import_interleaved_save(forged)

    def test_oversized_and_unsupported_structures_are_bounded(self):
        p,g,s,c,t=self.source()
        good=export_interleaved_save(p,g,s,t,c)
        huge=deepcopy(good);huge["padding"]="x"*(MAX_SAVE_BYTES+1)
        with self.assertRaises(InterleavedSaveError):
            import_interleaved_save(huge)
        with self.assertRaises(InterleavedSaveError):
            import_interleaved_save([])
        with self.assertRaises(InterleavedSaveError):
            import_interleaved_save(None)
        with self.assertRaises(InterleavedSaveError):
            continue_interleaved_save(good,additional_timeline=[1]*100)

    def test_append_only_continuation_without_new_earned_action_is_denied(self):
        p,g,s,c,t=self.source()
        save=export_interleaved_save(p,g,s,t,c)
        with self.assertRaises(InterleavedSaveError):
            continue_interleaved_save(save)
        with self.assertRaises(InterleavedSaveError):
            continue_interleaved_save(save,additional_genre=g)
        with self.assertRaises(InterleavedSaveError):
            continue_interleaved_save(save,additional_timeline=[
                {"at":2,"lane":"genre","source_index":0,"event_index":0}])

    def test_saved_original_world_rules_and_proof_chain_are_not_client_owned(self):
        p,g,s,c,t=self.source()
        good=export_interleaved_save(p,g,s,t,c)
        cases=(
            lambda x:x.update(world_settings_digest="0"*64),
            lambda x:x.update(source_head_hash="0"*64),
            lambda x:x.update(true_genre_event_count=99),
            lambda x:x.update(world_actions=42),
        )
        for mutate in cases:
            forged=deepcopy(good);mutate(forged)
            with self.assertRaises(InterleavedSaveError):
                import_interleaved_save(forged)


if __name__=="__main__":
    unittest.main()
