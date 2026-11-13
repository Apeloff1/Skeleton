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

    def test_required_item_in_sealed_room_rejected_at_source(self):
        candidate = fixture(["#######", "#S.G###", "#######", "###.###", "#######"])
        candidate["objects"] = [{"id": "key", "kind": "item", "x": 3, "y": 3}]
        candidate["quests"] = [{"id": "unlock", "requires_items": ["key"],
                                "requires_npcs": [], "requires_quests": []}]
        candidate["endings"][0]["requires_quests"] = ["unlock"]
        with self.assertRaisesRegex(GameplayContractError, "unreachable interactive object"):
            Campaign.load(candidate)

    def test_all_isolated_interactive_object_kinds_denied(self):
        rows = ["#######", "#S.G###", "#######", "###.###", "#######"]
        for obj in (
            {"id": "secret", "kind": "item", "x": 3, "y": 3},
            {"id": "speaker", "kind": "npc", "x": 3, "y": 3},
            {"id": "guard", "kind": "enemy", "x": 3, "y": 3, "hp": 2, "attack": 1},
        ):
            with self.subTest(kind=obj["kind"]):
                candidate = fixture(rows)
                candidate["objects"] = [obj]
                with self.assertRaisesRegex(GameplayContractError, "unreachable interactive object"):
                    Campaign.load(candidate)

    def test_reachable_interactive_objects_remain_valid(self):
        candidate = fixture(["#######", "#S..G##", "#.....#", "#######"])
        candidate["objects"] = [{"id": "key", "kind": "item", "x": 3, "y": 2},
                                {"id": "friend", "kind": "npc", "x": 4, "y": 2}]
        candidate["quests"] = [{"id": "unlock", "requires_items": ["key"],
                                "requires_npcs": ["friend"], "requires_quests": []}]
        candidate["endings"][0]["requires_quests"] = ["unlock"]
        campaign = Campaign.load(candidate)
        self.assertEqual(campaign.start, (1, 1))

    def test_source_identity_rejects_foreign_restore(self):
        campaign = Campaign.load(fixture(["#####", "#S.G#", "#####"]))
        other = Campaign.load(fixture(["#####", "#SG.#", "#####"]))
        with self.assertRaises(GameplayContractError):
            Session.restore(other, Session.new(campaign).snapshot())


if __name__ == "__main__":
    unittest.main()
