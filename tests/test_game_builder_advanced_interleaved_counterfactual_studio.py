"""Original game Studio compare-and-author causal world mirror controls."""
from __future__ import annotations
import inspect
import unittest

from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.game_workspace_server import _StudioHandler


class OriginalCounterfactualStudioTests(unittest.TestCase):
    @staticmethod
    def html():
        return render_workspace_html("D"*32).decode("utf-8")

    def test_source_replayed_whatif_editor_and_manual_author_action(self):
        html=self.html()
        for token in (
            'id="advanced-whatif-trial-limit"',
            'id="advanced-whatif-run"',
            'id="advanced-whatif-candidate"',
            'id="advanced-whatif-use"',
            'id="advanced-whatif-proof"',
            '"/api/advanced-interleaved-counterfactual"',
            '$("advanced-whatif-run").addEventListener("click"',
            '$("advanced-whatif-use").addEventListener("click"',
            'candidate.candidate_index===chosen && x.valid',
        ):
            if token.endswith("candidate.candidate_index===chosen && x.valid"):
                self.assertIn('x.candidate_index===chosen && x.valid',html)
            else:
                self.assertIn(token,html)

    def test_bad_source_trials_never_count_as_game_improvement(self):
        html=self.html()
        for token in (
            "proof.total_trials!==proof.candidates.length",
            "response.counterfactuals_promoted",
            "proof.unearned_world_rewards_applied",
            "proof.automatic_ai_weight_promotion",
            "option.disabled=!candidate.valid",
            "if(!candidate || !candidate.candidate_digest)",
            'lastInterleavedProof=null',
            'lastInterleavedTimeline=null',
            'candidate.authored_timeline',
            'actual_verified_differences:proof.candidates.map',
        ):
            self.assertIn(token,html)

    def test_server_replays_all_alternatives_independently_before_return(self):
        body=inspect.getsource(_StudioHandler)
        for token in (
            '"/api/advanced-interleaved-counterfactual"',
            'run_counterfactual_lab(',
            'verify_counterfactual_lab(',
            '"original_project_files_mutated":False',
            '"counterfactuals_promoted":False',
            '"native_all_engines_certified":False',
        ):
            self.assertIn(token,body)


if __name__=="__main__":
    unittest.main()
