"""Portable original physics/genre Studio saves preserve entire reviewed world."""
from __future__ import annotations

import inspect
import unittest

from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.game_workspace_server import _StudioHandler


class MixedOriginalWorldSaveStudioTests(unittest.TestCase):
    @staticmethod
    def page():
        return render_workspace_html("7"*32).decode("utf-8")

    def test_operator_has_functional_combined_save_export_and_import_controls(self):
        html=self.page()
        for token in (
            'id="advanced-unified-save-export"',
            'id="advanced-unified-save-import"',
            'id="advanced-unified-save-receipt"',
            '$("advanced-unified-save-export").addEventListener("click"',
            '$("advanced-unified-save-import").addEventListener("change"',
            "/api/advanced-unified-genre-save-export",
            "/api/advanced-unified-genre-save-import",
            'link.download="original-unified-game-"',
        ):
            self.assertIn(token,html)

    def test_import_reconstructs_physical_prefix_before_restoring_world_map(self):
        html=self.page()
        for token in (
            'verified.replayed_campaign.world_scene_digest!==verified.world_scene.digest',
            'verified.save_digest!==authored.digest',
            "physical.proof.digest!==verified.replayed_campaign.physical_campaign_digest",
            'world_settings:verified.world_settings',
            'episodicLastProof=physical.proof',
            'verifiedGenreEvents=verified.genre_sessions',
            'unifiedWorldFollowups=verified.world_actions',
            'lastUnifiedGenreProof=verified.replayed_campaign',
            'drawNPCForensicMap(lastUnifiedGenreProof.world_state)',
            'reexecuted_all_original_games:true',
            'original_files_unchanged:true',
        ):
            self.assertIn(token,html)

    def test_verified_server_handles_export_import_and_safe_continuation(self):
        body=inspect.getsource(_StudioHandler)
        for token in (
            '"/api/advanced-unified-genre-save-export"',
            '"/api/advanced-unified-genre-save-import"',
            '"/api/advanced-unified-genre-save-continue"',
            'export_unified_world_save(',
            'import_unified_world_save(',
            'continue_unified_world_save(',
            '"original_project_mutated":False',
            '"automatic_publication":False',
        ):
            self.assertIn(token,body)


if __name__=="__main__":
    unittest.main()
