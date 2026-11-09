"""Original RPG AI director proves witnessed choices and a real chapter."""
from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_rpg_planner import (
    RPGPlanningError,plan_original_rpg_chapter,verify_original_rpg_plan,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    run_advanced_session,verify_advanced_session,
)


class OriginalRPGPlannerTests(unittest.TestCase):
    def test_director_replays_real_witnessed_quest_chain(self):
        scene=make_advanced_scene("rpg")
        result=plan_original_rpg_chapter(scene)
        self.assertEqual(result["status"],"replay_verified_chapter")
        self.assertEqual(set(result["earned_quests"]),
                         {"recover_relic","resolve_dispute","clear_threat"})
        self.assertTrue(result["independent_replay_verified"])
        self.assertTrue(result["postgame_available"])
        self.assertFalse(result["native_hardware_verified"])
        self.assertTrue(verify_original_rpg_plan(result,scene))
        receipt=run_advanced_session("rpg",actions=result["actions"],scene=scene)
        self.assertTrue(receipt["state"]["chapter_claimed"])
        self.assertFalse(receipt["state"]["finished"])
        self.assertTrue(verify_advanced_session(receipt))
        self.assertEqual(result["replay_digest"],receipt["digest"])

    def test_diplomatic_choice_changes_recorded_faction_history(self):
        scene=make_advanced_scene("rpg")
        trusted=plan_original_rpg_chapter(scene,social_choice="choose:trust")
        challenged=plan_original_rpg_chapter(scene,social_choice="choose:challenge")
        self.assertEqual(trusted["status"],"replay_verified_chapter")
        self.assertEqual(challenged["status"],"replay_verified_chapter")
        self.assertGreater(trusted["resulting_faction_reputation"]["village"],
                           challenged["resulting_faction_reputation"]["village"])
        self.assertNotEqual(trusted["replay_digest"],challenged["replay_digest"])

    def test_small_budgets_are_inconclusive_not_unwinnable(self):
        scene=make_advanced_scene("rpg")
        result=plan_original_rpg_chapter(scene,max_actions=4)
        self.assertEqual(result["status"],"inconclusive_bounded_story")
        self.assertFalse(result["independent_replay_verified"])
        self.assertFalse(result["exhaustive_search_proved"])
        self.assertTrue(verify_original_rpg_plan(result,scene))

    def test_forged_memories_or_nonfinite_budget_rejected(self):
        scene=make_advanced_scene("rpg")
        proof=plan_original_rpg_chapter(scene,max_actions=4)
        for edit in (
            lambda r:r.update(source_digest="0"*64),
            lambda r:r.update(status="replay_verified_chapter"),
            lambda r:r.update(best_partial_position=[999,999]),
            lambda r:r.update(max_actions=5),
            lambda r:r.update(digest="forgery"),
        ):
            attack=deepcopy(proof);edit(attack)
            with self.assertRaises(RPGPlanningError):
                verify_original_rpg_plan(attack,scene)
        for kwargs in (
            {"max_nodes":True},{"max_nodes":8001},
            {"max_actions":129},{"social_choice":"choose:teleport"},
        ):
            with self.assertRaises(RPGPlanningError):
                plan_original_rpg_chapter(scene,**kwargs)


if __name__=="__main__":
    unittest.main()
