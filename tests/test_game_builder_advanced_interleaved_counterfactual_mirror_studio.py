"""Real source-verified original-world counterfactual Studio controls."""
from __future__ import annotations
import inspect
import unittest
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.game_workspace_server import _StudioHandler


class OriginalGameMirrorStudioTests(unittest.TestCase):
    @staticmethod
    def html():
        return render_workspace_html("A"*32).decode("utf-8")

    def test_authored_scenario_editor_requires_real_original_source_event_order(self):
        html=self.html()
        for value in (
            'id="advanced-mirror-build"',
            'id="advanced-mirror-objective"',
            'id="advanced-mirror-scenarios"',
            'id="advanced-mirror-run"',
            'id="advanced-mirror-proof"',
            '$("advanced-mirror-build").addEventListener',
            '$("advanced-mirror-run").addEventListener',
            'lastInterleavedTimeline',
            'a.lane==="physical"&&b.lane==="genre"',
            'alternate.forEach((event,index)=>{event.at=index;})',
        ):
            self.assertIn(value,html)

    def test_narrow_factual_objectives_never_claim_general_ai_improvement(self):
        html=self.html()
        for value in (
            'value="site_integrity"',
            'value="direct_memories"',
            'value="supplies"',
            'value="quests_completed"',
            'proof.universal_game_quality_claimed',
            'proof.automatic_model_training_approved',
            'objective_only_ranking:proof.ranking_for_this_metric_only',
            'factual_change_from_baseline:x.difference_from_first',
            'universal_quality_or_ai_model_improvement_proven:false',
        ):
            self.assertIn(value,html)

    def test_server_replays_every_original_candidate_and_denies_client_scores(self):
        text=inspect.getsource(_StudioHandler)
        for value in (
            '"/api/advanced-interleaved-counterfactuals"',
            'run_interleaved_counterfactuals(',
            'verify_interleaved_counterfactuals(',
            '"original_files_changed":False',
            '"automatic_ai_promotion":False',
            '"universal_game_quality_approved":False',
        ):
            self.assertIn(value,text)


if __name__=="__main__":
    unittest.main()
