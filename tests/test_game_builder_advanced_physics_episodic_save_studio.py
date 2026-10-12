"""Studio-bound portable episodic saves are source-replayed and operator-controlled."""
from __future__ import annotations

import inspect
import unittest
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.game_workspace_server import _StudioHandler


class PortableCampaignStudioTests(unittest.TestCase):
    @staticmethod
    def html():
        return render_workspace_html("E"*32).decode("utf-8")

    def test_real_operator_save_export_and_file_import(self):
        page=self.html()
        for token in (
            'id="advanced-episodic-save-export"',
            'id="advanced-episodic-save-import"',
            'id="advanced-episodic-save-receipt"',
            '/api/advanced-physics-episodic-save-export',
            '/api/advanced-physics-episodic-save-import',
            'link.download="original-npc-physics-campaign-"',
            'const document=JSON.parse(raw)',
        ):
            self.assertIn(token,page)

    def test_import_requires_independent_reconstruction_before_world_render(self):
        page=self.html()
        for token in (
            'imported?.verified',
            'imported.save_digest!==document.digest',
            'response.original_source_modified',
            'response.native_hardware_certified',
            'response.automatic_publication_approved',
            'imported.campaign.world_scene_digest!==imported.world_scene.digest',
            'verifiedSourceEpisodes=imported.episodes',
            'drawNPCForensicMap(episodicLastProof.world_state)',
            'remaining_episodes:imported.remaining_episode_budget',
        ):
            self.assertIn(token,page)

    def test_server_has_immutable_save_and_restore_paths(self):
        source=inspect.getsource(_StudioHandler)
        for token in (
            '"/api/advanced-physics-episodic-save-export"',
            '"/api/advanced-physics-episodic-save-import"',
            '"/api/advanced-physics-episodic-save-continue"',
            'export_episodic_savegame(',
            'import_episodic_savegame(',
            'continue_episodic_savegame(',
            '"original_source_modified":False',
            '"automatic_publication_approved":False',
        ):
            self.assertIn(token,source)


if __name__=="__main__":
    unittest.main()
