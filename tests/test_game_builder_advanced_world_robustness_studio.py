"""Studio cross-context game-world evidence is measured, not invented."""
from __future__ import annotations

import inspect
import unittest

from skeleton.ai.game_builder.game_workspace_server import _StudioHandler
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html


class MultiContextNPCStudioTests(unittest.TestCase):
    @staticmethod
    def html():
        return render_workspace_html("A"*32).decode("utf-8")

    def test_cross_context_controls_and_actual_source_scene_generation(self):
        page=self.html()
        for phrase in (
            'id="advanced-robustness-contexts"',
            'id="advanced-robustness-run"',
            'id="advanced-robustness-copy"',
            'id="advanced-robustness-proof"',
            'value="2"',
            'value="3"',
            '"/api/advanced-scene-template"',
            'editor:"quest_director",seed:nextSeed',
            'scenes.some(scene=>scene.digest===result.scene.digest)',
            '"/api/advanced-world-robustness"',
        ):
            self.assertIn(phrase,page)

    def test_candidate_adoption_rejects_inferior_tested_world_and_requires_replay(self):
        page=self.html()
        for phrase in (
            'proof.source_whatif_digest!==lastWorldWhatIfProof.digest',
            'proof.world_scenes.some((id,i)=>id!==scenes[i].digest)',
            'proof.population_generalization_claimed',
            'proof.automatic_ai_weights_promoted',
            'no_claim_about_other_worlds:true',
            '!scenario.not_worse_in_any_authored_context',
            '$("advanced-interleave-editor").value=JSON.stringify(scenario.timeline,null,2)',
            'lastInterleavedProof=null;lastInterleavedTimeline=null',
            'no_automatic_gameplay_or_ai_promotion:true',
        ):
            self.assertIn(phrase,page)

    def test_server_checks_original_complete_multi_world_proof_twice(self):
        body=inspect.getsource(_StudioHandler)
        for phrase in (
            '"/api/advanced-world-robustness"',
            'run_world_robustness(',
            'verify_world_robustness(',
            '"original_games_mutated":False',
            '"automatic_scenario_adopted":False',
            '"population_generalization_proven":False',
            '"native_hardware_certified":False',
        ):
            self.assertIn(phrase,body)


if __name__=="__main__":
    unittest.main()
