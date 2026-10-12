"""Local Studio authored physics/NPC causality UX and custody regression tests."""
from __future__ import annotations

import unittest

from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.game_workspace_server import _StudioHandler


class PhysicalNPCLocalStudioTests(unittest.TestCase):
    @staticmethod
    def html():
        return render_workspace_html("A"*32).decode("utf-8")

    def test_visual_original_source_and_site_binding_is_not_decorative(self):
        content=self.html()
        for item in (
            'id="advanced-npc-source"',
            'id="advanced-npc-site"',
            'id="advanced-npc-followups"',
            'id="advanced-npc-observe"',
            'id="advanced-npc-evidence"',
            'Reconstruct physical incident and NPC eyewitness quests',
            'source_fixture_impacts',
            'source_id:sourceId,site_id:site',
            '"quest_director"',
            'original_causal_quests',
            'first_hand_witnesses',
            'eyewitness:n.memories,rumors:n.heard',
        ):
            self.assertIn(item,content)

    def test_studio_never_claims_game_mutation_unearned_rewards_or_native_certification(self):
        content=self.html()
        self.assertIn('reply.source_project_mutated',content)
        self.assertIn('reply.native_certified',content)
        self.assertIn('reply.automatic_quest_reward_granted_to_original_game',content)
        self.assertIn('original_project_mutated:false',content)
        self.assertIn('reply.proof.world_scene_digest!==world.scene.digest',content)
        self.assertIn('reply.proof.source_session_digest!==advancedSession.digest',content)

    def test_server_handler_supports_verified_npc_source_contract(self):
        # The API is same-origin and authenticated by the enclosing workspace
        # handler, not by a client-authorized result or an arbitrary source URL.
        import inspect
        source=inspect.getsource(_StudioHandler)
        self.assertIn('"/api/advanced-physics-npc-witness"',source)
        self.assertIn('verify_physical_witness_world(',source)
        self.assertIn('"automatic_quest_reward_granted_to_original_game":False',source)
        self.assertIn('"source_project_mutated":False',source)


if __name__=="__main__":
    unittest.main()
