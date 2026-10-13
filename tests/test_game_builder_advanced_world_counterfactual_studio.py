"""Studio what-if UI never treats guessed alternate histories as valid rewards."""
from __future__ import annotations
import inspect
import unittest

from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.game_workspace_server import _StudioHandler


class WorldCounterfactualStudioTests(unittest.TestCase):
    @staticmethod
    def html():
        return render_workspace_html("9"*32).decode("utf-8")

    def test_real_typed_source_research_controls_and_objectives(self):
        page=self.html()
        for token in (
            'id="advanced-counterfactual-objective"',
            'value="preserve_sites"',
            'value="retain_supplies"',
            'value="maximize_earned_quests"',
            'value="maximize_firsthand_memories"',
            'id="advanced-counterfactual-generate"',
            'id="advanced-counterfactual-cases"',
            'id="advanced-counterfactual-run"',
            'id="advanced-counterfactual-choice"',
            'id="advanced-counterfactual-select"',
            'id="advanced-counterfactual-report"',
            '$("advanced-counterfactual-run").addEventListener("click"',
        ):
            self.assertIn(token,page)

    def test_source_baseline_must_be_fresh_and_all_comparisons_are_replayed(self):
        page=self.html()
        for token in (
            '"/api/advanced-world-counterfactuals"',
            'proof.baseline_world_digest!==lastInterleavedProof.digest',
            'proof.candidate_count!==variants.length',
            'proof.original_game_files_changed',
            'proof.automatic_world_promotion_approved',
            'response.automatic_scenario_accepted',
            'response.native_hardware_certified',
            'trial.status!=="valid"',
            'e.difference_from_baseline',
            'source_replay_digest:proof.digest',
        ):
            self.assertIn(token,page)

    def test_explicit_selection_edits_source_schedule_and_requires_replay(self):
        page=self.html()
        for token in (
            '$("advanced-counterfactual-select").addEventListener("click"',
            'e=>e.id===id && e.status==="valid" && e.actual_world_digest',
            '$("advanced-interleave-editor").value=JSON.stringify(trial.timeline,null,2)',
            'lastInterleavedProof=null;',
            'lastInterleavedTimeline=null;',
            'replay the original world clock to enact it',
            'no_automatic_selection:true',
        ):
            self.assertIn(token,page)

    def test_server_reconstructs_every_scenario_and_verifies_report(self):
        source=inspect.getsource(_StudioHandler)
        for token in (
            '"/api/advanced-world-counterfactuals"',
            'derive_counterfactuals(values["timeline"])',
            'run_counterfactual_laboratory(',
            'verify_counterfactual_laboratory(',
            '"original_source_projects_changed":False',
            '"automatic_scenario_accepted":False',
            '"automatic_ai_weight_promotion":False',
        ):
            self.assertIn(token,source)


if __name__=="__main__":
    unittest.main()
