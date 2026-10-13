"""Human-reviewed if/all/any/not NPC world source rules in local Studio."""
from __future__ import annotations

import inspect
import unittest
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.game_workspace_server import _StudioHandler


class NPCConditionalStudioTests(unittest.TestCase):
    @staticmethod
    def page():
        return render_workspace_html("8"*32).decode("utf-8")

    def test_actual_original_world_rule_editor_and_buttons(self):
        html=self.page()
        for part in (
            'id="advanced-npc-rule-editor"',
            'id="advanced-npc-rule-preview"',
            'id="advanced-npc-rule-commit"',
            'id="advanced-npc-rule-proof"',
            'when:{all:[',
            '{any:[',
            'fact:"source_eyewitnesses"',
            'fact:"player_supplies"',
            '/api/advanced-npc-conditional-world',
            'runNPCConditionalRules("preview")',
            'runNPCConditionalRules("commit")',
        ):
            self.assertIn(part,html)

    def test_only_server_proof_can_author_original_quest_actions(self):
        html=self.page()
        for part in (
            'proof.source_campaign_digest!==before',
            'proof.world_scene_digest!==episodicLastScene.digest',
            'proof.source_game_files_mutated',
            'proof.unearned_npc_rewards_granted',
            'mode==="commit" && proof.applied_effects>0',
            'verifiedSourceEpisodes=proof.episodes',
            '$("advanced-episodic-play").click()',
            'original_source_files_unchanged:true',
        ):
            self.assertIn(part,html)

    def test_same_origin_server_uses_independent_signed_rule_replay(self):
        source=inspect.getsource(_StudioHandler)
        for part in (
            '"/api/advanced-npc-conditional-world"',
            'run_npc_conditional_rules(',
            'verify_npc_conditional_rules(',
            'authorized=mode=="commit"',
            '"original_project_files_modified":False',
            '"native_hardware_verified":False',
            '"automatic_promotion_approved":False',
        ):
            self.assertIn(part,source)


if __name__=="__main__":
    unittest.main()
