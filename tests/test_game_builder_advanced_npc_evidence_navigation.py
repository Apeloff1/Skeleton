"""Verified physical paths to authentic eyewitnesses and world repairs."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import run_advanced_session
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_physics_episodic_world import (
    run_episodic_physics_world,
)
from skeleton.ai.game_builder.advanced_npc_evidence_navigation import (
    MAX_MOVES,EvidenceNavigationError,
    navigate_verified_investigation,verify_investigation_navigation,
)


class AuthoredForensicRouteTests(unittest.TestCase):
    @staticmethod
    def settings(**extra):
        return {
            "witnesses_required":1,"night_sight_penalty":0,
            "npc_perception":3,"witness_radius":3,"memory_decay_ticks":0,
            "event_rules":4,"quest_ttl":80,
            "npc_autonomy":False,"npc_mobility":False,
            **extra
        }

    @classmethod
    def campaign(cls,opts=None,*,source_actions=(),world_actions=()):
        rules=opts if opts is not None else cls.settings()
        world=make_advanced_scene("quest_director",rules,seed=0)
        scene=make_advanced_scene("racing",seed=1)
        source=run_advanced_session("racing",actions=source_actions,
                                    seed=1,scene=scene)
        episode={
            "source_session":source,"source_settings":None,
            "physics_actions":["push:east"]*8,
            "bindings":[{"source_id":scene["layout"]["track_obstacle"],
                         "site_id":0}],
            "world_actions":list(world_actions)
        }
        return (run_episodic_physics_world([episode],world,rules),
                [episode],world,rules)

    def test_actual_source_eyewitness_interview_executes_real_tile_movement(self):
        proof,episodes,scene,rules=self.campaign()
        before=deepcopy(proof)
        route=navigate_verified_investigation(
            proof,episodes,scene,rules,quest_id=0,objective="testimony")
        self.assertEqual(proof,before)
        self.assertEqual(route["outcome"],"firsthand_testimony_recorded")
        self.assertIn("speak:0",route["planned_and_simulated_actions"])
        self.assertTrue(route["next_quest_state"]["testimonies"])
        self.assertLessEqual(len(route["planned_and_simulated_actions"]),MAX_MOVES)
        self.assertTrue(verify_investigation_navigation(
            route,proof,episodes,scene,rules))

    def test_routing_respects_real_walkable_tiles_and_stamina(self):
        proof,episodes,scene,rules=self.campaign()
        route=navigate_verified_investigation(
            proof,episodes,scene,rules,quest_id=0,objective="testimony")
        walls=set(scene["layout"]["obstacles"])
        old=proof["world_state"]["player"]
        for step in route["route_steps"]:
            if step["action"] in ("north","south","east","west"):
                nxt=step["player"]
                self.assertNotIn(nxt,walls)
                self.assertEqual(abs(old%7-nxt%7)+abs(old//7-nxt//7),1)
                old=nxt
        self.assertLess(route["end_world_state"]["stamina"],
                        proof["world_state"]["stamina"])

    def test_real_site_repair_spends_resources_instead_of_minting_them(self):
        proof,episodes,scene,rules=self.campaign()
        result=navigate_verified_investigation(
            proof,episodes,scene,rules,quest_id=0,objective="repair")
        self.assertEqual(result["outcome"],"real_site_repair_enacted")
        self.assertIn("repair:0",result["planned_and_simulated_actions"])
        self.assertGreater(result["end_world_state"]["sites"][0]["integrity"],
                           proof["world_state"]["sites"][0]["integrity"])
        self.assertLess(result["end_world_state"]["supplies"],
                        proof["world_state"]["supplies"])
        self.assertTrue(verify_investigation_navigation(
            result,proof,episodes,scene,rules))

    def test_earned_corroborated_material_quest_resolves_after_actual_walk(self):
        rules=self.settings(consequence_depth=1,evidence_min=1)
        proof,episodes,scene,rules=self.campaign(
            rules,world_actions=(
                "east","east","speak:0","choose:0:support",
                "west","repair:0"))
        active=next(q for q in proof["world_state"]["quests"] if
                    q["id"]==0)
        self.assertEqual(active["choice"],"support")
        self.assertGreaterEqual(active["material_actions"],1)
        self.assertGreaterEqual(len(active["testimonies"]),1)
        result=navigate_verified_investigation(
            proof,episodes,scene,rules,quest_id=0,objective="resolve")
        self.assertEqual(result["outcome"],"original_quest_resolved")
        self.assertEqual(result["next_quest_state"]["ending"],"restored")
        self.assertEqual(result["next_quest_state"]["status"],"resolved")
        self.assertEqual(result["end_world_state"]["quests_completed"],
                         proof["world_state"]["quests_completed"]+1)
        self.assertGreater(result["end_world_state"]["gold"],
                           proof["world_state"]["gold"])
        self.assertTrue(verify_investigation_navigation(
            result,proof,episodes,scene,rules))

    def test_unearned_quest_resolution_is_denied_even_when_site_is_nearby(self):
        proof,episodes,scene,rules=self.campaign()
        result=navigate_verified_investigation(
            proof,episodes,scene,rules,quest_id=0,objective="resolve")
        self.assertEqual(result["outcome"],
                         "real_material_or_testimony_prerequisites_missing")
        self.assertEqual(result["planned_and_simulated_actions"],[])
        self.assertEqual(result["end_world_state"]["quests_completed"],
                         proof["world_state"]["quests_completed"])
        self.assertTrue(verify_investigation_navigation(
            result,proof,episodes,scene,rules))

    def test_npc_direct_knowledge_cannot_be_replaced_with_rumor(self):
        rules=self.settings(memory_decay_ticks=1)
        proof,episodes,scene,rules=self.campaign(rules)
        result=navigate_verified_investigation(
            proof,episodes,scene,rules,quest_id=0,objective="testimony")
        self.assertNotEqual(result["outcome"],"firsthand_testimony_recorded")
        self.assertFalse(result["next_quest_state"]["testimonies"])
        self.assertTrue(verify_investigation_navigation(
            result,proof,episodes,scene,rules))

    def test_recommendation_itself_is_a_replayed_not_client_written_transcript(self):
        proof,episodes,scene,rules=self.campaign()
        approved=navigate_verified_investigation(
            proof,episodes,scene,rules,quest_id=0,objective="testimony")
        attempts=(
            lambda x:x["planned_and_simulated_actions"].append("teleport"),
            lambda x:x["route_steps"][0].update(player=48),
            lambda x:x["route_steps"][0].update(head_hash="0"*64),
            lambda x:x["next_quest_state"].update(testimonies=[999]),
            lambda x:x.update(outcome="original_quest_resolved"),
            lambda x:x.update(original_campaign_mutated=True),
        )
        for edit in attempts:
            forged=deepcopy(approved)
            edit(forged)
            with self.assertRaises(EvidenceNavigationError):
                verify_investigation_navigation(forged,proof,episodes,scene,rules)

    def test_altered_world_or_unknown_quest_target_does_not_plan_omniscient_path(self):
        proof,episodes,scene,rules=self.campaign()
        for qid in (True,-1,12,99):
            with self.assertRaises(EvidenceNavigationError):
                navigate_verified_investigation(
                    proof,episodes,scene,rules,quest_id=qid)
        with self.assertRaises(EvidenceNavigationError):
            navigate_verified_investigation(
                proof,episodes,scene,rules,quest_id=0,objective="mint_gold")
        with self.assertRaises(EvidenceNavigationError):
            navigate_verified_investigation(
                proof,episodes,scene,rules,quest_id=3)
        tampered=deepcopy(proof)
        tampered["world_state"]["npcs"][0]["cell"]=48
        with self.assertRaises(EvidenceNavigationError):
            navigate_verified_investigation(
                tampered,episodes,scene,rules,quest_id=0)

    def test_route_enacts_only_finite_original_world_commands(self):
        proof,episodes,scene,rules=self.campaign()
        result=navigate_verified_investigation(
            proof,episodes,scene,rules,quest_id=0,objective="testimony")
        from skeleton.ai.game_builder.advanced_quest_director_runtime import ACTIONS
        self.assertTrue(all(action in ACTIONS for action
                            in result["planned_and_simulated_actions"]))
        self.assertEqual(len(result["route_steps"]),
                         len(result["planned_and_simulated_actions"]))
        self.assertFalse(result["automatic_rewards_or_publication"])


if __name__=="__main__":
    unittest.main()
