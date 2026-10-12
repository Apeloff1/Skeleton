"""Portable original interleaved world clock Studio and source-only import."""
from __future__ import annotations
import inspect
import unittest

from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.game_workspace_server import _StudioHandler


class InterleavedOriginalSaveStudioTests(unittest.TestCase):
    @staticmethod
    def markup():
        return render_workspace_html("F"*32).decode("utf-8")

    def test_file_export_import_are_real_same_origin_ui_controls(self):
        html=self.markup()
        for phrase in (
            'id="advanced-interleave-save-export"',
            'id="advanced-interleave-save-import"',
            'id="advanced-interleave-save-proof"',
            '$("advanced-interleave-save-export").addEventListener("click"',
            '$("advanced-interleave-save-import").addEventListener("change"',
            '"/api/advanced-interleaved-save-export"',
            '"/api/advanced-interleaved-save-import"',
            'link.download="original-interleaved-game-"',
        ):
            self.assertIn(phrase,html)

    def test_reimport_requires_full_replay_and_does_not_invent_physics_prefix(self):
        html=self.markup()
        for phrase in (
            'restored?.verified',
            'restored.save_digest!==authored.digest',
            'response.original_files_changed',
            'response.native_full_world_certified',
            'response.automatic_publishing_approved',
            'restored.replayed_world.world_scene_digest!==restored.world_scene.digest',
            'verifiedSourceEpisodes=restored.physical_episodes',
            'verifiedGenreEvents=restored.genre_sessions',
            'interleavedWorldSettings=restored.world_settings',
            'episodicLastProof=null',
            'lastInterleavedTimeline=restored.timeline',
            'drawNPCForensicMap(restored.replayed_world.world_state)',
            'complete_original_game_replay:true',
        ):
            self.assertIn(phrase,html)

    def test_server_owns_original_save_and_append_only_continue_verification(self):
        body=inspect.getsource(_StudioHandler)
        for phrase in (
            '"/api/advanced-interleaved-save-export"',
            '"/api/advanced-interleaved-save-import"',
            '"/api/advanced-interleaved-save-continue"',
            'export_interleaved_save(',
            'import_interleaved_save(',
            'continue_interleaved_save(',
            '"original_files_changed":False',
            '"automatic_publishing_approved":False',
        ):
            self.assertIn(phrase,body)


if __name__=="__main__":
    unittest.main()
