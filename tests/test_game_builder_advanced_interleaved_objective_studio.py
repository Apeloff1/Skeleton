"""Actual original game design metrics, Pareto candidates and Studio approval."""
from __future__ import annotations
import inspect
import unittest
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.game_workspace_server import _StudioHandler


class OriginalNPCObjectiveStudioTests(unittest.TestCase):
    @staticmethod
    def html():
        return render_workspace_html("E"*32).decode("utf-8")

    def test_user_can_review_real_source_measured_objective_tradeoffs(self):
        text=self.html()
        for token in (
            'id="advanced-objective-goals"',
            'id="advanced-objective-run"',
            'id="advanced-objective-proof"',
            'credible_eyewitness_reach',
            'earned_quest_completions',
            'original_site_restoration',
            'finite_material_resilience',
            '/api/advanced-interleaved-objectives',
            'independently_better_cases:matrix.verified_strict_improvements',
            'actual_story_tradeoffs:matrix.observed_tradeoffs',
            'pareto_nondominated:c.pareto_frontier',
        ):
            self.assertIn(token,text)

    def test_comparison_never_auto_applies_quests_or_model_promotion(self):
        text=self.html()
        for token in (
            'result.source_project_files_mutated',
            'result.objective_ranking_auto_applied',
            'result.ai_model_promotion_approved',
            'matrix.automatic_game_event_application',
            'matrix.automatic_ai_weight_promotion',
            'JSON.stringify(matrix.goals)!==JSON.stringify(goalList)',
            'matrix.max_candidates!==maxCandidates',
            'matrix.candidate_count!==matrix.candidate_results.length',
            'suggested_only_if_strictly_better:matrix.suggested_candidate_index',
            'candidate_selection_requires_separate_manual_whatif_review:true',
        ):
            self.assertIn(token,text)

    def test_server_replays_original_source_games_and_objective_claims(self):
        body=inspect.getsource(_StudioHandler)
        for token in (
            '"/api/advanced-interleaved-objectives"',
            'run_causal_objective_matrix(',
            'verify_causal_objective_matrix(',
            '"source_project_files_mutated":False',
            '"objective_ranking_auto_applied":False',
            '"ai_model_promotion_approved":False',
        ):
            self.assertIn(token,body)


if __name__=="__main__":
    unittest.main()
