"""User-facing real material-aid completion and audited original relief UI."""
from __future__ import annotations

import unittest

from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html


class MaterialReliefStudioTests(unittest.TestCase):
    @staticmethod
    def html():
        return render_workspace_html("C"*32).decode("utf-8")

    def test_relief_is_actual_playable_quest_objective(self):
        content=self.html()
        for value in (
            'value="aid"',
            'Deliver finite relief supplies for recovery quests',
            'verifiedInvestigationRoute.outcome!=="finite_original_community_aid_delivered"',
            "latest.world_actions.push(...realMoves)",
            '$("advanced-episodic-play").click()',
        ):
            self.assertIn(value,content)

    def test_real_material_aid_history_is_exposed_as_world_source(self):
        content=self.html()
        self.assertIn('original_relief_deliveries:proof.world_state.relief_deliveries',content)
        self.assertIn('source_games_unchanged:true',content)
        self.assertIn('proof.world_state.sites',content)


if __name__=="__main__":
    unittest.main()
