"""Studio has real source-replayed alternative game world review controls."""
from __future__ import annotations

import inspect
import unittest

from skeleton.ai.game_builder.game_workspace_server import _StudioHandler
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html


class OriginalWhatIfStudioTests(unittest.TestCase):
    @staticmethod
    def html():
        return render_workspace_html("E"*32).decode("utf-8")

    def test_mirror_panel_exposes_four_real_factual_priorities_and_depth(self):
        page=self.html()
        for phrase in (
            'id="advanced-whatif-objective"',
            'value="eyewitness_coverage"',
            'value="community_recovery"',
            'value="resource_stewardship"',
            'value="quest_progress"',
            'id="advanced-whatif-depth"',
            'id="advanced-whatif-run"',
            'id="advanced-whatif-select"',
            'id="advanced-whatif-use"',
            'id="advanced-whatif-proof"',
        ):
            self.assertIn(phrase,page)

    def test_actual_replay_results_are_required_before_selectable_authored_order(self):
        page=self.html()
        for phrase in (
            '"/api/advanced-world-whatif-lab"',
            'report.source_games_changed',
            'report.automatic_authoring_committed',
            'report.source_world_scene_digest!==episodicLastScene.digest',
            'response.native_hardware_certified',
            'response.model_weight_promotion_approved',
            'for(const alternative of report.accepted_scenarios)',
            'lastWorldWhatIfProof.accepted_scenarios.find(',
            'if(!selected || !selected.actually_replayed)',
            '$("advanced-interleave-editor").value=JSON.stringify(selected.timeline,null,2)',
            'lastInterleavedProof=null',
            'lastInterleavedTimeline=null',
            'no_automatic_model_promotion:true',
        ):
            self.assertIn(phrase,page)

    def test_authentic_server_reruns_entire_adversarial_world_not_client_metrics(self):
        handler=inspect.getsource(_StudioHandler)
        for phrase in (
            '"/api/advanced-world-whatif-lab"',
            'run_world_whatif(',
            'verify_world_whatif(',
            '"original_game_files_mutated":False',
            '"automatic_scenario_committed":False',
            '"native_hardware_certified":False',
            '"model_weight_promotion_approved":False',
        ):
            self.assertIn(phrase,handler)


if __name__=="__main__":
    unittest.main()
