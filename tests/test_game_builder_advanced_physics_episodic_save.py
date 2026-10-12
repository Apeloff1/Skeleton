"""Tamper-resistant portable saves for independently replayed game worlds."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import run_advanced_session
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_physics_episodic_save import (
    SCHEMA,MAX_SAVE_BYTES,EpisodicSaveError,
    export_episodic_savegame,import_episodic_savegame,
    continue_episodic_savegame,
)


class OriginalEpisodicSaveTests(unittest.TestCase):
    @staticmethod
    def opts():
        return {
            "witnesses_required":1,"night_sight_penalty":0,
            "npc_perception":3,"witness_radius":3,"memory_decay_ticks":0,
            "event_rules":4,"quest_ttl":80,"npc_autonomy":False,
            "npc_mobility":False,
        }

    @classmethod
    def initial(cls):
        config=cls.opts()
        world=make_advanced_scene("quest_director",config,seed=0)
        source=make_advanced_scene("racing",seed=1)
        first=run_advanced_session("racing",seed=1,scene=source)
        episode={
            "source_session":first,
            "source_settings":None,
            "physics_actions":["push:east"]*8,
            "bindings":[{"source_id":source["layout"]["track_obstacle"],"site_id":0}],
            "world_actions":["wait"],
        }
        return [episode],world,config

    def test_complete_original_world_roundtrip(self):
        episodes,scene,cfg=self.initial()
        source=deepcopy(episodes)
        save=export_episodic_savegame(episodes,scene,cfg)
        assert save["schema"]==SCHEMA
        self.assertEqual(save["episode_count"],1)
        restored=import_episodic_savegame(save)
        self.assertTrue(restored["verified"])
        self.assertEqual(restored["campaign"]["digest"],save["campaign_digest"])
        self.assertEqual(restored["campaign"]["head_hash"],save["head_hash"])
        self.assertEqual(restored["episodes"],episodes)
        self.assertEqual(episodes,source)
        self.assertEqual(restored["campaign"]["world_state"]["turn"],2)
        self.assertFalse(restored["automatic_publication_approved"])

    def test_original_save_can_append_world_actions_without_state_injection(self):
        episodes,scene,cfg=self.initial()
        saved=export_episodic_savegame(episodes,scene,cfg)
        later=continue_episodic_savegame(saved,additional_world_actions=("wait","inspect"))
        imported=import_episodic_savegame(later)
        self.assertEqual(imported["campaign"]["world_state"]["turn"],4)
        self.assertEqual(imported["episodes"][-1]["world_actions"],
                         ["wait","wait","inspect"])
        self.assertEqual(import_episodic_savegame(saved)["campaign"]["world_state"]["turn"],2)
        self.assertNotEqual(later["digest"],saved["digest"])

    def test_multiple_source_episodes_are_persisted_in_order(self):
        episodes,scene,cfg=self.initial()
        source=episodes[0]["source_session"]["scene"]
        advanced=run_advanced_session("racing",actions=("accelerate",),seed=1,
                                      scene=source)
        future=deepcopy(episodes[0])
        future["source_session"]=advanced
        future["bindings"][0]["site_id"]=1
        save=export_episodic_savegame(episodes,scene,cfg)
        continuation=continue_episodic_savegame(save,additional_episodes=[future])
        result=import_episodic_savegame(continuation)
        self.assertEqual(result["campaign"]["episode_count"],2)
        self.assertEqual(result["campaign"]["world_state"]["turn"],4)
        self.assertEqual([event["site_id"] for event in
                          result["campaign"]["world_state"]["events_log"]],[0,1])

    def test_forged_game_health_witness_and_reward_cannot_recompute_valid_save(self):
        episodes,scene,cfg=self.initial()
        good=export_episodic_savegame(episodes,scene,cfg)
        variants=[
            lambda x:x["episodes"][0]["source_session"]["state"].update(fuel=9999),
            lambda x:x["episodes"][0]["source_session"]["state"].update(
                finished=True),
            lambda x:x["episodes"][0]["bindings"][0].update(site_id=3),
            lambda x:x.update(world_state_digest="0"*64),
            lambda x:x.update(campaign_digest="0"*64),
        ]
        import hashlib,json
        for change in variants:
            tampered=deepcopy(good);change(tampered)
            # An attacker can recompute an outer SHA, but cannot generate
            # authentic canonical source and physical world replay receipts.
            fields={k:v for k,v in tampered.items() if k!="digest"}
            tampered["digest"]=hashlib.sha256(json.dumps(
                fields,sort_keys=True,separators=(",",":"),
                ensure_ascii=True,allow_nan=False).encode()).hexdigest()
            with self.assertRaises(EpisodicSaveError):
                import_episodic_savegame(tampered)

    def test_import_denies_unknown_fields_false_release_claims_and_wide_input(self):
        episodes,scene,cfg=self.initial()
        good=export_episodic_savegame(episodes,scene,cfg)
        for field,value in (
            ("native_device_certified",True),
            ("automatic_promotion_approved",True),
            ("requires_full_local_replay",False),
            ("original_game_saves_mutated",True),
            ("schema","evil"),
            ("episode_count",True),
        ):
            forged=deepcopy(good);forged[field]=value
            with self.assertRaises(EpisodicSaveError):
                import_episodic_savegame(forged)
        forged=deepcopy(good);forged["extra_client_state"]={"gold":999}
        with self.assertRaises(EpisodicSaveError):
            import_episodic_savegame(forged)
        forged=deepcopy(good);forged["padding"]="x"*(MAX_SAVE_BYTES+1)
        with self.assertRaises(EpisodicSaveError):
            import_episodic_savegame(forged)

    def test_replay_and_source_identity_cannot_roll_back_or_duplicate(self):
        episodes,scene,cfg=self.initial()
        good=export_episodic_savegame(episodes,scene,cfg)
        with self.assertRaises(EpisodicSaveError):
            continue_episodic_savegame(good,additional_episodes=episodes)
        with self.assertRaises(EpisodicSaveError):
            continue_episodic_savegame(good,additional_world_actions=["teleport"])
        with self.assertRaises(EpisodicSaveError):
            continue_episodic_savegame(good,additional_world_actions=["wait"]*24)
        with self.assertRaises(EpisodicSaveError):
            continue_episodic_savegame(good)
        self.assertEqual(import_episodic_savegame(good)["campaign"]["episode_count"],1)

    def test_episodic_scene_seed_and_settings_remain_replay_bound(self):
        episodes,scene,cfg=self.initial()
        original=export_episodic_savegame(episodes,scene,cfg)
        altered=deepcopy(original)
        altered["world_scene"]=make_advanced_scene("quest_director",cfg,seed=1)
        with self.assertRaises(EpisodicSaveError):
            import_episodic_savegame(altered)
        altered=deepcopy(original)
        altered["world_settings_digest"]="a"*64
        with self.assertRaises(EpisodicSaveError):
            import_episodic_savegame(altered)


if __name__=="__main__":
    unittest.main()
