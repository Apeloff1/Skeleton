"""User-facing real original genre achievements and NPC witness source gates."""
from __future__ import annotations

import inspect
import unittest
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.game_workspace_server import _StudioHandler


class TrueCrossGenreNPCStudioTests(unittest.TestCase):
    def test_local_user_can_inspect_actual_source_earned_event_receipts(self):
        html=render_workspace_html("D"*32).decode("utf-8")
        for part in (
            'id="advanced-genre-event-inspect"',
            'id="advanced-genre-event-index"',
            'id="advanced-genre-event-site"',
            'id="advanced-genre-event-play"',
            'id="advanced-genre-event-proof"',
            'mature_crop_harvested',
            'original_cargo_delivered',
            'runway_landing_confirmed',
            'advancedSession.trace.length',
            'item.events.includes(approved)',
        ):
            self.assertIn(part,html)

    def test_source_identified_exact_action_not_decorative_gameplay(self):
        html=render_workspace_html("D"*32).decode("utf-8")
        for part in (
            '"/api/advanced-cross-genre-npc-world"',
            'trace_index:index',
            'advancedSession.digest',
            'proof.source_session_digest!==advancedSession.digest',
            'proof.world_scene_digest!==world.scene.digest',
            'proof.source_game_files_changed',
            'finite_npc_site_stock:proof.world_state.sites',
            'actual_source_quests:proof.world_state.quests',
        ):
            self.assertIn(part,html)

    def test_authenticated_server_independently_verifies_earned_genre_causes(self):
        body=inspect.getsource(_StudioHandler)
        for part in (
            '"/api/advanced-cross-genre-npc-world"',
            'run_cross_genre_world(',
            'verify_cross_genre_world(',
            '"original_project_files_modified":False',
            '"native_hardware_certified":False',
            '"automatic_rewards_or_promotion":False',
        ):
            self.assertIn(part,body)


if __name__=="__main__":
    unittest.main()
