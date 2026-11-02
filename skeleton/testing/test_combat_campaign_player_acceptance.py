"""Player-driven combat acceptance from source to terminal export."""
from __future__ import annotations

import copy
import unittest

from skeleton.game.gameplay.combat_campaign import original_campaign
from skeleton.game.gameplay.combat_campaign_player import demo_player_campaign
from skeleton.game.gameplay.combat_campaign_player_acceptance import (
    MAX_TRANSCRIPT_BYTES, _BoundedWriter, accept_player_campaign,
    original_player_acceptance, verify_player_acceptance,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


class CombatPlayerAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = original_campaign()
        self.actions = [event["action"] for event in demo_player_campaign()["journal"]]

    def test_original_human_campaign_end_to_end(self) -> None:
        receipt = original_player_acceptance()
        self.assertEqual(receipt["status"], "playable_verified")
        self.assertEqual(receipt["action_count"], len(self.actions))
        self.assertEqual(verify_player_acceptance(receipt, self.source), receipt)
        self.assertGreater(receipt["earned_currency"], 0)

    def test_nonwinning_prefix_and_invalid_batch_rejected(self) -> None:
        with self.assertRaises(CombatSessionError):
            accept_player_campaign(self.source, self.actions[:1])
        for invalid in ([], None, "invalid", [None] * 33):
            with self.assertRaises(CombatSessionError):
                accept_player_campaign(self.source, invalid)

    def test_source_drift_and_forged_receipt_rejected(self) -> None:
        receipt = original_player_acceptance()
        source = copy.deepcopy(self.source)
        source["encounters"][0]["reward"] += 1
        with self.assertRaises(CombatSessionError):
            verify_player_acceptance(receipt, source)
        forged = copy.deepcopy(receipt)
        forged["earned_currency"] += 100
        with self.assertRaises(CombatSessionError):
            verify_player_acceptance(forged, self.source)

    def test_transcript_limit_fails_closed(self) -> None:
        writer = _BoundedWriter()
        writer.write("x" * MAX_TRANSCRIPT_BYTES)
        with self.assertRaisesRegex(CombatSessionError, "budget"):
            writer.write("y")


if __name__ == "__main__":
    unittest.main()
