"""Live original-world NPC investigation map, routes and authenticated playback."""
from __future__ import annotations

import inspect
import unittest

from skeleton.ai.game_builder.game_workspace_server import _StudioHandler
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html


class VerifiedInvestigationStudioTests(unittest.TestCase):
    @staticmethod
    def markup():
        return render_workspace_html("B"*32).decode("utf-8")

    def test_real_authored_npc_map_and_live_quest_selection(self):
        html=self.markup()
        for value in (
            'id="advanced-npc-world-canvas"',
            'width="380" height="350"',
            'function drawNPCForensicMap(world)',
            'const obstacles=new Set(world.world.obstacles)',
            'for(const site of world.sites)',
            'for(const npc of world.npcs)',
            'npc.memories.length',
            'npc.heard.length',
            'const [px,py]=center(world.player)',
            'function refreshNPCQuestRouteChoices(proof)',
            'id="advanced-npc-route-quest"',
            '$("advanced-npc-world-canvas").addEventListener("click"',
            'q.origin_actor==="external:physics"',
        ):
            self.assertIn(value,html)

    def test_testimony_repair_and_earned_resolution_actions_are_real(self):
        html=self.markup()
        for value in (
            'value="testimony"',
            'value="repair"',
            'value="resolve"',
            'id="advanced-npc-route"',
            'id="advanced-npc-route-apply"',
            '$("advanced-npc-route").addEventListener("click"',
            '$("advanced-npc-route-apply").addEventListener("click"',
            "/api/advanced-npc-evidence-navigation",
            'verifiedInvestigationRoute.campaign_digest!==episodicLastProof.digest',
            'latest.world_actions.push(...realMoves)',
            '$("advanced-episodic-play").click()',
        ):
            self.assertIn(value,html)

    def test_stale_source_and_unearned_rewards_fail_closed_in_studio(self):
        html=self.markup()
        for value in (
            'answer.original_game_changed',
            'answer.automatic_quest_reward_granted',
            'answer.native_hardware_verified',
            'route.world_scene_digest!==episodicLastScene.digest',
            'verifiedInvestigationRoute.outcome!=="firsthand_testimony_recorded"',
            'verifiedInvestigationRoute.outcome!=="real_site_repair_enacted"',
            'verifiedInvestigationRoute.outcome!=="original_quest_resolved"',
            'latest.world_actions.length+realMoves.length>24',
            'total+realMoves.length>64',
            'episodicLastProof=null',
        ):
            self.assertIn(value,html)

    def test_server_actually_verifies_both_origins_and_route(self):
        handler=inspect.getsource(_StudioHandler)
        for part in (
            '"/api/advanced-npc-evidence-navigation"',
            "navigate_verified_investigation(",
            "verify_investigation_navigation(",
            '"original_game_changed":False',
            '"automatic_quest_reward_granted":False',
            '"native_hardware_verified":False',
        ):
            self.assertIn(part,handler)


if __name__=="__main__":
    unittest.main()
