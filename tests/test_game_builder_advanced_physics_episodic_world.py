"""Episodic original-game physical incidents in a persistent living NPC world."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import run_advanced_session
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_physics_episodic_world import (
    EpisodicWorldError,MAX_EPISODES,run_episodic_physics_world,
    verify_episodic_physics_world,
)


class EpisodicPhysicalWorldTests(unittest.TestCase):
    @staticmethod
    def settings():
        return {
            "witnesses_required":1,"night_sight_penalty":0,
            "npc_perception":3,"witness_radius":3,"memory_decay_ticks":0,
            "event_rules":4,"quest_ttl":80,"npc_autonomy":False,
            "npc_mobility":False,
        }

    @classmethod
    def world(cls):
        opts=cls.settings()
        return opts,make_advanced_scene("quest_director",opts,seed=0)

    @staticmethod
    def source(actions=(),editor="racing",seed=1):
        scene=make_advanced_scene(editor,seed=seed)
        return run_advanced_session(
            editor,actions=actions,seed=seed,scene=scene)

    @staticmethod
    def episode(source,site=0,phys=None,world_actions=()):
        source_id=(source["scene"]["layout"]["track_obstacle"]
                   if source["editor"]=="racing" else
                   source["scene"]["layout"]["hazards"][0])
        return {
            "source_session":source,
            "source_settings":None,
            "physics_actions":list(phys or ("push:east",)*8),
            "bindings":[{"source_id":source_id,"site_id":site}],
            "world_actions":list(world_actions),
        }

    def test_real_two_episode_campaign_preserves_npc_quests_and_site_damage(self):
        cfg,world=self.world()
        first=self.source()
        second=self.source(("accelerate",))
        turns=[self.episode(first,site=0,world_actions=("wait","inspect")),
               self.episode(second,site=1,world_actions=("wait",))]
        original=deepcopy(turns)
        proof=run_episodic_physics_world(turns,world,cfg)
        self.assertEqual(turns,original)
        self.assertEqual(proof["episode_count"],2)
        self.assertEqual(proof["total_true_incidents"],2)
        self.assertEqual(proof["world_state"]["turn"],5)
        self.assertEqual(len(proof["world_state"]["events_log"]),2)
        self.assertEqual([x["site_id"] for x in proof["world_state"]["events_log"]],
                         [0,1])
        self.assertGreaterEqual(len(proof["world_state"]["quests"]),2)
        self.assertTrue(all(x["applied_incidents"] for x in proof["episodes"]))
        self.assertEqual(proof["world_state"]["reputation"],cfg.get("starting_reputation",0))
        self.assertTrue(verify_episodic_physics_world(proof,turns,world,cfg))

    def test_actual_evasive_lane_causes_no_incident_in_one_episode(self):
        cfg,world=self.world()
        first=self.source()
        avoided=self.source(("steer_right",))
        proof=run_episodic_physics_world([
            self.episode(first,site=0),self.episode(avoided,site=1)
        ],world,cfg)
        self.assertEqual(proof["total_true_incidents"],1)
        self.assertEqual(proof["episodes"][1]["applied_incidents"],[])
        self.assertEqual(len(proof["world_state"]["events_log"]),1)

    def test_world_commands_must_be_an_array_not_a_mapping_or_string(self):
        cfg,world=self.world()
        base=self.episode(self.source())
        for invalid in ({"wait":True}, "wait", 4, None):
            with self.subTest(actions=invalid):
                episode=deepcopy(base)
                episode["world_actions"]=invalid
                with self.assertRaises(EpisodicWorldError):
                    run_episodic_physics_world([episode],world,cfg)
        self.assertTrue(verify_episodic_physics_world(
            run_episodic_physics_world([base],world,cfg),[base],world,cfg))

    def test_same_original_scene_must_strictly_extend_source_transcript(self):
        cfg,world=self.world()
        initial=self.source()
        next_session=self.source(("accelerate",))
        future=self.source(("accelerate","coast"))
        proof=run_episodic_physics_world([
            self.episode(initial),self.episode(next_session,site=1),
            self.episode(future,site=2)
        ],world,cfg)
        self.assertEqual(proof["episode_count"],3)
        self.assertEqual(proof["world_state"]["turn"],3)
        self.assertTrue(verify_episodic_physics_world(proof,[
            self.episode(initial),self.episode(next_session,site=1),
            self.episode(future,site=2)],world,cfg))

    def test_replayed_source_receipt_cannot_duplicate_incident_or_reward(self):
        cfg,world=self.world()
        first=self.source()
        for duplicate in (
            [self.episode(first),self.episode(first,site=1)],
            [self.episode(first),
             self.episode(first,site=1,phys=("push:east",)*7)],
        ):
            with self.assertRaises(EpisodicWorldError):
                run_episodic_physics_world(duplicate,world,cfg)

    def test_source_different_games_are_kept_as_independent_custody(self):
        cfg,world=self.world()
        racing=self.source()
        platformer=self.source(editor="platformer")
        proof=run_episodic_physics_world([
            self.episode(racing,site=0),
            self.episode(platformer,site=1)
        ],world,cfg)
        self.assertEqual([ep["source_editor"] for ep in proof["episodes"]],
                         ["racing","platformer"])
        self.assertEqual(proof["episode_count"],2)
        self.assertTrue(verify_episodic_physics_world(proof,[
            self.episode(racing,site=0),self.episode(platformer,site=1)
        ],world,cfg))

    def test_previous_world_memory_survives_source_episode_boundary(self):
        cfg,world=self.world()
        first=self.source()
        next_session=self.source(("accelerate",))
        proof=run_episodic_physics_world([
            self.episode(first,site=0,world_actions=("wait:4",)),
            self.episode(next_session,site=1,world_actions=("wait:4",))
        ],world,cfg)
        log=proof["world_state"]["events_log"]
        self.assertEqual([x["id"] for x in log],[0,1])
        self.assertGreater(proof["episodes"][1]["world_tick"],
                           proof["episodes"][0]["world_tick"])
        self.assertTrue(any(0 in [m["event_id"] for m in npc["memories"]]
                    for npc in proof["world_state"]["npcs"]))

    def test_forged_episode_hash_world_damage_and_witnesses_are_rejected(self):
        cfg,world=self.world()
        episode=self.episode(self.source())
        proof=run_episodic_physics_world([episode],world,cfg)
        cases=(
            lambda x:x["episodes"][0]["applied_incidents"][0].update(
                        contact_count=987),
            lambda x:x["episodes"][0].update(head_hash="0"*64),
            lambda x:x["world_state"]["sites"][0].update(integrity=999),
            lambda x:x["episodes"][0]["applied_incidents"][0][
                "real_world_event"].update(direct_witnesses=[999]),
            lambda x:x.update(total_true_incidents=99),
            lambda x:x.update(original_source_games_unchanged=False),
        )
        for alter in cases:
            forged=deepcopy(proof)
            alter(forged)
            with self.assertRaises(EpisodicWorldError):
                verify_episodic_physics_world(forged,[episode],world,cfg)

    def test_unknown_world_actions_and_overlong_episodes_fail_closed(self):
        cfg,world=self.world()
        first=self.source()
        for actions in (["teleport"],["wait"]*25,["wait",None]):
            with self.assertRaises(EpisodicWorldError):
                run_episodic_physics_world(
                    [self.episode(first,world_actions=actions)],world,cfg)
        with self.assertRaises(EpisodicWorldError):
            run_episodic_physics_world(
                [self.episode(first)]*(MAX_EPISODES+1),world,cfg)

    def test_wrong_world_seed_or_modified_original_source_fails_replay(self):
        cfg,world=self.world()
        episode=self.episode(self.source())
        report=run_episodic_physics_world([episode],world,cfg)
        newer=make_advanced_scene("quest_director",cfg,seed=2)
        with self.assertRaises(EpisodicWorldError):
            verify_episodic_physics_world(report,[episode],newer,cfg)
        changed=deepcopy(episode)
        changed["source_session"]["state"]["fuel"]=999
        with self.assertRaises(EpisodicWorldError):
            verify_episodic_physics_world(report,[changed],world,cfg)


if __name__=="__main__":
    unittest.main()
