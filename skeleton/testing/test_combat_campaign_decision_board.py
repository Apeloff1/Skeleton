"""Source-bound human combat decision previews and conservation contracts."""
from __future__ import annotations

import copy
import unittest

from skeleton.game.gameplay.combat_campaign import original_campaign
from skeleton.game.gameplay.combat_campaign_player import (
    demo_player_campaign, new_player_campaign, resume_player_campaign,
    verify_player_campaign,
)
from skeleton.game.gameplay.combat_campaign_decision_board import decision_board
from skeleton.game.gameplay.turn_combat import CombatSessionError


class CombatDecisionBoardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.start = new_player_campaign(original_campaign())

    def test_all_choices_are_canonical_and_input_immutable(self) -> None:
        saved = copy.deepcopy(self.start)
        board = decision_board(self.start)
        self.assertEqual(self.start, saved)
        self.assertEqual(board["state_digest"], self.start["state_digest"])
        self.assertGreaterEqual(len(board["choices"]), 3)
        for choice in board["choices"]:
            replayed = resume_player_campaign(self.start, [choice["action"]])
            self.assertEqual(replayed["state_digest"], choice["state_digest"])
            self.assertEqual(replayed["state"]["currency"], choice["currency"])
            self.assertGreaterEqual(choice["earned_currency_delta"], 0)
        self.assertFalse(board["choices_truncated"])

    def test_source_lease_and_forged_state_rejected(self) -> None:
        with self.assertRaisesRegex(CombatSessionError, "stale"):
            decision_board(self.start, expected_source_digest="0" * 64)
        forged = copy.deepcopy(self.start)
        forged["state"]["hero_hp"] = 0
        with self.assertRaises(CombatSessionError):
            decision_board(forged)

    def test_terminal_campaign_has_no_new_actions(self) -> None:
        final = demo_player_campaign()
        board = decision_board(final)
        self.assertEqual(board["choices"], [])
        self.assertEqual(board["phase"], final["state"]["phase"])

    def test_budgets_are_strict_and_truncation_explicit(self) -> None:
        for value in (0, True, 17):
            with self.assertRaises(CombatSessionError):
                decision_board(self.start, max_choices=value)
        board = decision_board(self.start, max_choices=1)
        self.assertEqual(len(board["choices"]), 1)
        self.assertTrue(board["choices_truncated"])
        self.assertEqual(verify_player_campaign(self.start), self.start)


if __name__ == "__main__":
    unittest.main()
