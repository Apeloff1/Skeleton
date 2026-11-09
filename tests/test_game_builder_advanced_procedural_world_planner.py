"""Original AI expedition planning cannot mistake a nonterminal world for victory."""
from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_procedural_world_planner import (
    FrontierPlanningError,plan_original_frontier,verify_original_frontier_plan,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    run_advanced_session,verify_advanced_session,
)


class FrontierPlannerTests(unittest.TestCase):
    def test_nonterminal_expedition_is_really_playable_after_last_landmark(self):
        for storage in ("rebuild","save_deltas","snapshot"):
            settings={"persistence":storage}
            scene=make_advanced_scene("procedural_world",settings)
            result=plan_original_frontier(scene,settings)
            self.assertEqual(result["status"],"replay_verified_expedition")
            self.assertTrue(result["world_still_playable"])
            self.assertFalse(result["retired"])
            self.assertTrue(result["independent_replay_verified"])
            self.assertTrue(verify_original_frontier_plan(result,scene,settings))
            game=run_advanced_session("procedural_world",settings,
                                      result["actions"],scene=scene)
            self.assertTrue(game["state"]["expedition_complete"])
            self.assertFalse(game["state"]["finished"])
            self.assertEqual(result["replay_digest"],game["digest"])
            self.assertTrue(verify_advanced_session(game,settings))

    def test_explicit_requested_retirement_returns_home_and_ends_run(self):
        scene=make_advanced_scene("procedural_world")
        report=plan_original_frontier(scene,retire=True)
        self.assertEqual(report["status"],"replay_verified_expedition")
        self.assertTrue(report["retired"])
        self.assertFalse(report["world_still_playable"])
        proof=run_advanced_session("procedural_world",actions=report["actions"],
                                   scene=scene)
        self.assertEqual(proof["state"]["position"],[0,0])
        self.assertTrue(proof["state"]["retired"])
        self.assertTrue(verify_advanced_session(proof))

    def test_bounded_search_is_not_false_claim_of_world_unsolvability(self):
        scene=make_advanced_scene("procedural_world")
        receipt=plan_original_frontier(scene,max_actions=3)
        self.assertEqual(receipt["status"],"inconclusive_bounded_exploration")
        self.assertFalse(receipt["exhaustive_search_proved"])
        self.assertFalse(receipt["independent_replay_verified"])
        self.assertEqual(receipt["actions"],[])
        self.assertTrue(verify_original_frontier_plan(receipt,scene))

    def test_receipt_forgery_or_invalid_types_cannot_skip_real_steps(self):
        scene=make_advanced_scene("procedural_world")
        receipt=plan_original_frontier(scene,max_actions=3)
        for edit in (
            lambda r:r.update(status="replay_verified_expedition"),
            lambda r:r.update(best_partial_position=[500,500]),
            lambda r:r.update(source_digest="f"*64),
            lambda r:r.update(requested_retirement=True),
            lambda r:r.update(digest="invalid"),
        ):
            altered=deepcopy(receipt);edit(altered)
            with self.assertRaises(FrontierPlanningError):
                verify_original_frontier_plan(altered,scene)
        for kwargs in (
            {"max_actions":0},{"max_actions":129},
            {"max_actions":True},{"retire":1},
        ):
            with self.assertRaises(FrontierPlanningError):
                plan_original_frontier(scene,**kwargs)


if __name__=="__main__":
    unittest.main()
