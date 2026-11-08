"""Regression for source admission of reachable original grid campaigns."""
import copy
import unittest

from skeleton.game.gameplay.offline_grid_campaign import Campaign, Session, Command
from skeleton.game.gameplay.flgb_gameplay_runtime import GameplayContractError


def fixture(rows):
    return {
        "version": 1, "game_id": "reachability", "title": "Original Grid",
        "license": "CC0-1.0", "author": "studio_b",
        "rows": rows, "objects": [], "quests": [],
        "endings": [{"id": "victory", "requires_quests": [], "outcome": "victory"}],
    }


class ReachableGoalTests(unittest.TestCase):
    def test_reachable_game_can_end_and_restore(self):
        campaign = Campaign.load(fixture(["#####", "#S.G#", "#####"]))
        state = Session.new(campaign)
        state = state.step(Command("move1", "move", "east"))
        state = state.step(Command("move2", "move", "east"))
        state = state.step(Command("end1", "finish", "victory"))
        self.assertEqual(state.ending, "victory")
        self.assertEqual(Session.restore(campaign, state.snapshot()), state)

    def test_disconnected_goal_rejected_at_source_admission(self):
        with self.assertRaisesRegex(GameplayContractError, "unreachable"):
            Campaign.load(fixture(["#####", "#S#G#", "#####"]))

    def test_detour_around_wall_remains_playable(self):
        campaign = Campaign.load(fixture(["#######", "#S#..G#", "#.....#", "#######"]))
        self.assertEqual(campaign.start, (1, 1))

    def test_source_identity_rejects_foreign_restore(self):
        campaign = Campaign.load(fixture(["#####", "#S.G#", "#####"]))
        other = Campaign.load(fixture(["#####", "#SG.#", "#####"]))
        with self.assertRaises(GameplayContractError):
            Session.restore(other, Session.new(campaign).snapshot())


if __name__ == "__main__":
    unittest.main()
