"""Replay-proved civic AI chooses finite witnessed original social actions."""
from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_npc_society_planner import (
    CivicPlanningError,plan_original_civic_milestone,verify_original_civic_plan,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    run_advanced_session,verify_advanced_session,
)


class OriginalCivicPlannerTests(unittest.TestCase):
    SETTINGS={"simulation_lod":"background","coarse_period":16}

    def test_replays_two_real_witnesses_and_nonterminal_civic_achievement(self):
        scene=make_advanced_scene("npc_society",self.SETTINGS)
        receipt=plan_original_civic_milestone(scene,self.SETTINGS)
        self.assertEqual(receipt["status"],"replay_verified_civic_resolution")
        self.assertEqual(receipt["witnesses"],[0,1])
        self.assertTrue(receipt["world_still_playable"])
        self.assertTrue(receipt["independent_replay_verified"])
        self.assertTrue(verify_original_civic_plan(receipt,scene,self.SETTINGS))
        game=run_advanced_session(
            "npc_society",self.SETTINGS,receipt["actions"],scene=scene
        )
        self.assertTrue(game["state"]["incident_resolved"])
        self.assertTrue(game["state"]["community_checkpoint"])
        self.assertTrue(verify_advanced_session(game,self.SETTINGS))
        self.assertEqual(receipt["replay_digest"],game["digest"])

    def test_explicit_home_retirement_is_actual_world_action(self):
        scene=make_advanced_scene("npc_society",self.SETTINGS)
        result=plan_original_civic_milestone(scene,self.SETTINGS,retire=True)
        self.assertEqual(result["status"],"replay_verified_civic_resolution")
        self.assertTrue(result["retired"])
        self.assertFalse(result["world_still_playable"])
        self.assertTrue(verify_original_civic_plan(result,scene,self.SETTINGS))

    def test_search_budget_limits_are_inconclusive_not_unwinnable(self):
        scene=make_advanced_scene("npc_society",self.SETTINGS)
        report=plan_original_civic_milestone(scene,self.SETTINGS,max_actions=3)
        self.assertEqual(report["status"],"inconclusive_bounded_civic_search")
        self.assertFalse(report["independent_replay_verified"])
        self.assertFalse(report["exhaustive_search_proved"])
        self.assertTrue(verify_original_civic_plan(report,scene,self.SETTINGS))

    def test_tampered_history_and_untyped_retirement_are_refused(self):
        scene=make_advanced_scene("npc_society",self.SETTINGS)
        receipt=plan_original_civic_milestone(scene,self.SETTINGS,max_actions=3)
        for mutate in (
            lambda r:r.update(status="replay_verified_civic_resolution"),
            lambda r:r.update(best_partial_evidence=["fraud"]),
            lambda r:r.update(max_actions=4),
            lambda r:r.update(source_digest="x"*64),
            lambda r:r.update(digest="fraud"),
        ):
            forged=deepcopy(receipt);mutate(forged)
            with self.assertRaises(CivicPlanningError):
                verify_original_civic_plan(forged,scene,self.SETTINGS)
        for options in ({"max_actions":True},{"max_actions":129},
                        {"max_actions":0},{"retire":1}):
            with self.assertRaises(CivicPlanningError):
                plan_original_civic_milestone(scene,self.SETTINGS,**options)


if __name__=="__main__":
    unittest.main()
