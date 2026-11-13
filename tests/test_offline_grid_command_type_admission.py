"""Fail-closed command admission after P0 grid and save source convergence.

The latest main campaign and durable-save implementation remain authoritative.
A malformed JSON kind or target may never throw TypeError or become a valid command.
"""
import unittest

from skeleton.game.gameplay.offline_grid_campaign import Command, GameplayContractError


class CommandTypeAdmissionTests(unittest.TestCase):
    def test_reject_non_string_kinds_as_contract_errors(self):
        for kind in (None, True, False, 0, 1.0, [], {}, ["move"], {"move": 1}):
            with self.subTest(kind=repr(kind)), self.assertRaises(GameplayContractError):
                Command("bad_kind", kind, "north")

    def test_reject_non_string_targets_as_contract_errors(self):
        for target in (None, True, False, 0, 1.0, [], {}, ["north"], {"north": 1}):
            for kind in ("move", "wait", "collect"):
                with self.subTest(kind=kind, target=repr(target)), self.assertRaises(GameplayContractError):
                    Command("bad_target", kind, target)

    def test_supported_original_commands_are_unchanged(self):
        cases = [("move", "north"), ("wait", ""), ("collect", "coin"),
                 ("talk", "guide"), ("craft", "blade"), ("strike", "foe"),
                 ("finish", "ending")]
        for kind, target in cases:
            with self.subTest(kind=kind):
                action = Command("legitimate_action", kind, target)
                self.assertEqual((action.kind, action.target), (kind, target))


if __name__ == "__main__":
    unittest.main()
