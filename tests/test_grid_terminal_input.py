"""Keyboard-to-canonical-action tests; no mock gameplay engine."""
from __future__ import annotations
import unittest

from skeleton.game.gameplay.flgb_gameplay_runtime import GameplayContractError
from skeleton.game.gameplay.grid_terminal_input import parse_terminal_input
from skeleton.game.gameplay.offline_grid_campaign import Campaign, Session
from scripts.game.offline_grid_campaign import DEFAULT_SOURCE, _read


class TerminalInputTests(unittest.TestCase):
    def test_keyboard_and_arrows_translate_to_canonical_replay(self):
        for key, direction in (("w", "north"), ("A", "west"),
                               ("down", "south"), ("RIGHT", "east")):
            with self.subTest(key=key):
                command = parse_terminal_input(key, "key-1")
                self.assertEqual((command.kind, command.target),
                                 ("move", direction))

    def test_rejects_ambiguous_and_untrusted_input(self):
        for line in ("w north", "wait target", "north", "w\nquit",
                     "move", "move diagonal", "x" * 129, "collect"):
            with self.subTest(line=line):
                with self.assertRaises(GameplayContractError):
                    parse_terminal_input(line, "key-1")

    def test_valid_action_does_not_bypass_collision_or_replay(self):
        session = Session.new(Campaign.load(_read(DEFAULT_SOURCE)))
        command = parse_terminal_input("w", "key-1")
        try:
            advanced = session.step(command)
        except GameplayContractError:
            self.assertEqual(session.tick, 0)
        else:
            self.assertEqual(advanced.tick, 1)
            self.assertEqual(Session.restore(session.campaign, advanced.snapshot()),
                             advanced)


if __name__ == "__main__":
    unittest.main()
