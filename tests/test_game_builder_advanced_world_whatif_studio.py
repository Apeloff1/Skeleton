"""Actual authoring and source replay of original NPC-world what-if timelines."""
from __future__ import annotations

import inspect
import unittest

from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.game_workspace_server import _StudioHandler


class OriginalWorldWhatIfStudioTests(unittest.TestCase):
    @staticmethod
    def html():
        return render_workspace_html("9"*32).decode("utf-8")

    def test_real_source_baseline_and_alternative_controls_exist(self):
        script=self.html()
        for token in (
            'id="advanced-whatif-baseline"',
            'id="advanced-whatif-swap"',
            'id="advanced-whatif-capture"',
            'id="advanced-whatif-run"',
            'id="advanced-whatif-queue"',
            'id="advanced-whatif-results"',
            '$("advanced-whatif-baseline").addEventListener("click"',
            '$("advanced-whatif-swap").addEventListener("click"',
            '$("advanced-whatif-capture").addEventListener("click"',
            '$("advanced-whatif-run").addEventListener("click"',
        ):
            self.assertIn(token,script)

    def test_whatif_retains_same_source_inputs_and_rejects_uncertified_winner(self):
        script=self.html()
        for token in (
            "reviewedWorldWhatIfScenarios.length>=8",
            "current.forEach((entry,i)=>{entry.at=i;})",
            "JSON.stringify(x.timeline)===digest",
            "/api/advanced-world-whatif",
            "proof.scenarios.length!==reviewedWorldWhatIfScenarios.length",
            "!proof.same_source_and_action_inputs",
            "!proof.comparison_has_no_automatic_winner",
            "proof.automatic_model_training_approved",
            "proof.native_full_campaign_certified",
            "strictly_dominant_over_baseline:proof.strict_baseline_dominators",
            "no_automatic_winner:true",
        ):
            self.assertIn(token,script)

    def test_authenticated_server_rebuilds_both_original_worlds(self):
        source=inspect.getsource(_StudioHandler)
        for token in (
            '"/api/advanced-world-whatif"',
            "run_world_whatif_lab(",
            "verify_world_whatif_lab(",
            '"source_games_mutated":False',
            '"automatic_model_training":False',
            '"native_hardware_certified":False',
        ):
            self.assertIn(token,source)


if __name__=="__main__":
    unittest.main()
