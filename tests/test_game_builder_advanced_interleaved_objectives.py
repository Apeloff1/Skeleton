"""Original authored-game objective evaluation uses independently replayed worlds."""
from __future__ import annotations
from copy import deepcopy
import unittest

from tests import test_game_builder_advanced_interleaved_world as original_fixtures
from skeleton.ai.game_builder.advanced_interleaved_objectives import (
    SCHEMA,OBJECTIVES,ObjectiveMatrixError,
    run_causal_objective_matrix,verify_causal_objective_matrix,
    _dominates,
)


class OriginalGameObjectiveMatrixTests(unittest.TestCase):
    @staticmethod
    def source(*,kind="farming"):
        return original_fixtures.OriginalInterleavedWorldTests.inputs(genre=kind)

    @staticmethod
    def clock(*lanes):
        return original_fixtures.OriginalInterleavedWorldTests.timeline(*lanes)

    def test_independent_real_world_objectives_are_not_reorder_score_hype(self):
        physical,genres,scene,config=self.source()
        clock=self.clock("physical","genre")
        before=deepcopy((physical,genres,scene,config,clock))
        result=run_causal_objective_matrix(
            physical,genres,scene,clock,config,max_candidates=8)
        self.assertEqual((physical,genres,scene,config,clock),before)
        self.assertEqual(result["schema"],SCHEMA)
        self.assertEqual(result["candidate_count"],1)
        self.assertEqual(result["verified_valid_candidates"],1)
        self.assertEqual(result["baseline_metrics"]["earned_quest_completions"],0)
        self.assertEqual(result["verified_strict_improvements"],0)
        self.assertIsNone(result["suggested_candidate_index"])
        self.assertEqual(result["candidate_results"][0]["classification"],
                         "no_measured_gameplay_gain")
        self.assertTrue(verify_causal_objective_matrix(
            result,physical,genres,scene,clock,config))

    def test_authored_goal_order_is_explicit_and_replay_signed(self):
        p,g,s,c=self.source()
        clock=self.clock("genre","world","physical")
        goals=["finite_material_resilience","credible_eyewitness_reach",
               "earned_quest_completions"]
        report=run_causal_objective_matrix(
            p,g,s,clock,c,goals=goals,max_candidates=2)
        self.assertEqual(report["goals"],goals)
        self.assertEqual(report["max_candidates"],2)
        self.assertEqual(report["candidate_count"],2)
        self.assertEqual(report["baseline_goal_vector"],
                         [report["baseline_metrics"][goal] for goal in goals])
        self.assertTrue(verify_causal_objective_matrix(report,p,g,s,clock,c))

    def test_bounded_original_game_goals_fail_closed_before_executing_sources(self):
        p,g,s,c=self.source()
        clock=self.clock("physical","genre")
        invalid=(
            [],["unknown_goal"],["credible_eyewitness_reach"]*2,
            [False],["earned_quest_completions",3],
            list(OBJECTIVES),[["credible_eyewitness_reach"]],
        )
        for goals in invalid:
            with self.subTest(goals=goals),self.assertRaises(ObjectiveMatrixError):
                run_causal_objective_matrix(p,g,s,clock,c,goals=goals)

    def test_pareto_comparison_does_not_call_equal_or_regressed_scores_wins(self):
        self.assertFalse(_dominates([3,5],[3,5]))
        self.assertFalse(_dominates([3,4],[3,5]))
        self.assertFalse(_dominates([10,0],[9,1]))
        self.assertTrue(_dominates([4,5],[3,5]))
        self.assertTrue(_dominates([5,7],[4,6]))

    def test_real_maritime_resource_stock_is_measured_not_rewritten(self):
        p,g,s,c=self.source(kind="sailing")
        from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
        authored=deepcopy(s["layout"])
        authored["sites"][1]["stock"]=0
        s=make_advanced_scene("quest_director",c,seed=0,layout=authored)
        clock=self.clock("physical","genre")
        result=run_causal_objective_matrix(
            p,g,s,clock,c,goals=("finite_material_resilience",
                                 "original_site_restoration"),max_candidates=2)
        from skeleton.ai.game_builder.advanced_interleaved_world import (
            run_interleaved_world)
        actual=run_interleaved_world(p,g,s,clock,c)["world_state"]
        measured=sum(site["stock"] for site in actual["sites"])+actual["supplies"]
        self.assertEqual(result["baseline_metrics"]["finite_material_resilience"],
                         measured)
        self.assertEqual(result["candidate_results"][0]["measured_metrics"]
                         ["finite_material_resilience"],measured)
        self.assertTrue(verify_causal_objective_matrix(result,p,g,s,clock,c))

    def test_invalid_original_games_never_receive_favorable_objective_status(self):
        p,g,s,c=self.source()
        clock=self.clock("physical","genre")
        modified=deepcopy(g)
        modified[0]["source_session"]["state"]["harvested"]=999
        with self.assertRaises(ObjectiveMatrixError):
            run_causal_objective_matrix(p,modified,s,clock,c)

    def test_forged_goal_recommendation_is_rejected_by_real_game_replay(self):
        p,g,s,c=self.source()
        clock=self.clock("physical","genre")
        result=run_causal_objective_matrix(p,g,s,clock,c)
        attackers=(
            lambda x:x.update(verified_strict_improvements=99),
            lambda x:x.update(suggested_candidate_index=0),
            lambda x:x["candidate_results"][0].update(
                     strictly_better_than_baseline=True),
            lambda x:x["candidate_results"][0]["goal_deltas"].update(
                     earned_quest_completions=999),
            lambda x:x["candidate_results"][0].update(
                     pareto_frontier=not x["candidate_results"][0]["pareto_frontier"]),
            lambda x:x.update(automatic_ai_weight_promotion=True),
            lambda x:x.update(head_hash="0"*64),
        )
        for forge in attackers:
            bad=deepcopy(result);forge(bad)
            with self.assertRaises(ObjectiveMatrixError):
                verify_causal_objective_matrix(bad,p,g,s,clock,c)

    def test_all_world_objectives_stay_measured_on_actual_story_state(self):
        p,g,s,c=self.source()
        clock=self.clock("physical","world","genre","world")
        metrics=run_causal_objective_matrix(
            p,g,s,clock,c,
            goals=("credible_eyewitness_reach",
                   "earned_quest_completions",
                   "original_site_restoration",
                   "secondhand_rumor_reach"),
            max_candidates=3)
        self.assertEqual(metrics["candidate_count"],3)
        for candidate in metrics["candidate_results"]:
            if not candidate["valid"]:
                self.assertIsNone(candidate["measured_metrics"])
                self.assertFalse(candidate["pareto_frontier"])
                continue
            self.assertTrue(all(
                type(candidate["measured_metrics"][goal]) is int and
                candidate["measured_metrics"][goal]>=0
                for goal in OBJECTIVES))
            self.assertEqual(candidate["strictly_better_than_baseline"],
                             candidate["classification"]==
                             "strict_real_gameplay_improvement")
        self.assertTrue(verify_causal_objective_matrix(
            metrics,p,g,s,clock,c))


if __name__=="__main__":
    unittest.main()
