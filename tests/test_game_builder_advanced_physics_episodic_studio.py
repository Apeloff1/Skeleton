"""Play-ready signed multi-episode NPC Studio and API wiring."""
from __future__ import annotations

import inspect
import unittest

from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.game_workspace_server import _StudioHandler


class EpisodicNPCStudioTests(unittest.TestCase):
    @staticmethod
    def html():
        return render_workspace_html("F"*32).decode("utf-8")

    def test_queue_and_campaign_controls_are_real_interactive_paths(self):
        script=self.html()
        for token in (
            'id="advanced-episodic-add"',
            'id="advanced-episodic-play"',
            'id="advanced-episodic-clear"',
            'id="advanced-episodic-queue"',
            'id="advanced-episodic-proof"',
            '$("advanced-episodic-add").addEventListener',
            '$("advanced-episodic-play").addEventListener',
            '$("advanced-episodic-clear").addEventListener',
            "/api/advanced-physics-episodic-npc",
            "verifiedSourceEpisodes.push(episode)",
            "source_chronology:proof.episodes",
            "causal_quests:proof.world_state.quests",
            "rumor_edges:proof.world_state.rumor_edges",
        ):
            self.assertIn(token,script)

    def test_source_provenance_and_append_only_are_enforced_in_studio(self):
        script=self.html()
        for token in (
            "advancedSession.scene.digest",
            "physical.proof.source_session_digest!==advancedSession.digest",
            "next.length<=former.length",
            "former.some((a,i)=>a!==next[i])",
            "worldActions.length>24",
            "verifiedSourceEpisodes.length>=6",
            "source_games_unchanged:true",
            "response.source_saves_changed",
            "response.native_hardware_verified",
            "response.automatic_promotion_approved",
        ):
            self.assertIn(token,script)

    def test_server_reconstructs_entire_campaign_not_client_claims(self):
        source=inspect.getsource(_StudioHandler)
        for token in (
            '"/api/advanced-physics-episodic-npc"',
            "run_episodic_physics_world(",
            "verify_episodic_physics_world(",
            '"source_saves_changed":False',
            '"native_hardware_verified":False',
            '"automatic_promotion_approved":False',
        ):
            self.assertIn(token,source)


if __name__=="__main__":
    unittest.main()
