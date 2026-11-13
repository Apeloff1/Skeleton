"""Fail-closed input contracts for canonical offline campaign and replay."""
import unittest

from skeleton.game.gameplay.flgb_gameplay_runtime import GameplayContractError
from skeleton.game.gameplay.offline_grid_campaign import Campaign, Command, Session


SOURCE = {
    "version": 1, "game_id": "input-contract", "title": "Input Contract",
    "license": "CC0-1.0", "author": "original",
    "rows": ["#####", "#S.G#", "#####"], "objects": [], "quests": [],
    "endings": [{"id": "victory", "requires_quests": [], "outcome": "victory"}],
}


class CommandContractTests(unittest.TestCase):
    def setUp(self):
        self.campaign = Campaign.load(SOURCE)

    def test_reachable_ending_and_restart(self):
        session = Session.new(self.campaign)
        for index, (kind, target) in enumerate((
            ("move", "east"), ("move", "east"), ("finish", "victory"),
        ), 1):
            session = session.step(Command(f"step-{index}", kind, target))
        self.assertEqual(session.ending, "victory")
        self.assertEqual(Session.restore(self.campaign, session.snapshot()), session)

    def test_unhashable_direction_is_contract_error(self):
        for value in ([], {}, ["east"], {"east": True}, 3, True, None):
            with self.subTest(value=value), self.assertRaises(GameplayContractError):
                Command("move-invalid", "move", value)

    def test_malformed_action_kind_is_contract_error(self):
        for value in ([], {}, None, 1, True):
            with self.subTest(value=value), self.assertRaises(GameplayContractError):
                Command("kind-invalid", value, "")

    def test_failed_command_does_not_mutate_state(self):
        session = Session.new(self.campaign)
        original = session.snapshot()
        with self.assertRaises(GameplayContractError):
            session.step(Command("blocked", "move", "north"))
        self.assertEqual(session.snapshot(), original)

    def test_replay_rejects_malformed_target(self):
        session = Session.new(self.campaign).step(Command("step-1", "move", "east"))
        payload = session.snapshot()
        payload["events"][0]["target"] = []
        with self.assertRaises(GameplayContractError):
            Session.restore(self.campaign, payload)


if __name__ == "__main__":
    unittest.main()
