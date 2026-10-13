"""Authenticated unified original physics + genre world experience in Studio."""
from __future__ import annotations

import inspect
import unittest
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.game_workspace_server import _StudioHandler


class UnifiedGenreStudioTests(unittest.TestCase):
    @staticmethod
    def html():
        return render_workspace_html("6"*32).decode("utf-8")

    def test_real_user_controls_queue_play_and_clear_signed_achievements(self):
        page=self.html()
        for token in (
            'id="advanced-genre-queue"',
            'id="advanced-unified-run"',
            'id="advanced-genre-queue-clear"',
            'id="advanced-genre-queue-list"',
            'id="advanced-unified-proof"',
            '$("advanced-genre-queue").addEventListener',
            '$("advanced-unified-run").addEventListener',
            '$("advanced-genre-queue-clear").addEventListener',
            'verifiedGenreEvents.push({',
        ):
            self.assertIn(token,page)

    def test_original_session_and_world_digests_gate_every_committed_source(self):
        page=self.html()
        for token in (
            'verifiedGenreEvents.length>=4',
            'entry.source_session.digest===advancedSession.digest',
            'verified.report.source_session_digest!==advancedSession.digest',
            'verified.report.world_scene_digest!==episodicLastScene.digest',
            'result.source_project_files_modified',
            'proof.physical_campaign_digest!==episodicLastProof.digest',
            'proof.genre_session_count!==verifiedGenreEvents.length',
            'drawNPCForensicMap(proof.world_state)',
            'original_project_files_unchanged:true',
        ):
            self.assertIn(token,page)

    def test_server_replays_true_physical_and_genre_source_executable_gameplay(self):
        body=inspect.getsource(_StudioHandler)
        for token in (
            '"/api/advanced-unified-genre-campaign"',
            'run_unified_game_campaign(',
            'verify_unified_game_campaign(',
            '"source_project_files_modified":False',
            '"automatic_game_rewards":False',
            '"native_hardware_verified":False',
        ):
            self.assertIn(token,body)


if __name__=="__main__":
    unittest.main()
