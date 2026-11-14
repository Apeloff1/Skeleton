"""Author -> game -> deterministic checkpoint -> portable export acceptance."""
from __future__ import annotations

import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import unittest

from skeleton.game.gameplay.combat_campaign_author import demo_author
from skeleton.game.gameplay.combat_campaign_production_acceptance import (
    accept_production, cli, verify_production,
)
from skeleton.game.gameplay.combat_campaign_player import import_player_campaign
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError


class CampaignProductionAcceptanceTests(unittest.TestCase):
    def test_edited_source_reaches_real_playable_export(self) -> None:
        report = accept_production(demo_author())
        self.assertEqual(report["status"],
                         "source_to_play_to_save_replay_export_verified")
        self.assertEqual(report["earned_currency"], 32)
        self.assertGreater(len(report["player_actions"]), 0)
        self.assertEqual(report["playable_acceptance"]["earned_currency"], 32)
        self.assertEqual(report["source_digest"],
                         report["author_report"]["after_digest"])
        self.assertEqual(import_player_campaign(report["portable_bundle"]),
                         report["route_report"]["terminal_session"])
        self.assertEqual(verify_production(report), report)

    def test_budget_exhaustion_is_not_accepted_as_playability(self) -> None:
        with self.assertRaisesRegex(CombatSessionError, "proven playable victory"):
            accept_production(demo_author(), max_states=1)
        with self.assertRaisesRegex(CombatSessionError, "proven playable victory"):
            accept_production(demo_author(), max_depth=1)

    def test_tampered_source_reward_and_export_fail_closed(self) -> None:
        original = accept_production(demo_author())
        for mutate in (
            lambda x: x.update(earned_currency=999),
            lambda x: x["author_report"]["after"]["encounters"][0].update(reward=999),
            lambda x: x["portable_bundle"]["session"]["state"].update(currency=999),
            lambda x: x["player_actions"][0].update(kind="rest"),
        ):
            forged = copy.deepcopy(original)
            mutate(forged)
            forged["receipt"] = dig({k: v for k, v in forged.items()
                                     if k != "receipt"})
            with self.assertRaises(CombatSessionError):
                verify_production(forged)

    def test_reject_invalid_receipt_and_bad_author_report(self) -> None:
        receipt = accept_production(demo_author())
        forged = copy.deepcopy(receipt)
        forged["source_digest"] = "0" * 64
        with self.assertRaises(CombatSessionError):
            verify_production(forged)
        forged = copy.deepcopy(receipt)
        forged["route_report"]["limits"]["max_choices"] = 1
        forged["receipt"] = dig({k: v for k, v in forged.items()
                                 if k != "receipt"})
        with self.assertRaises(CombatSessionError):
            verify_production(forged)

    def test_cli_is_reachable_and_verifies_end_to_end(self) -> None:
        from skeleton.__main__ import main
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["combat-campaign-production-accept", "demo"]), 0)
        receipt = json.loads(output.getvalue())
        self.assertEqual(receipt["earned_currency"], 32)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(cli(["verify", "--receipt-json", json.dumps(receipt)]), 0)
        self.assertEqual(json.loads(output.getvalue()), receipt)
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(cli(["accept", "--author-report-json", "{}"]), 2)
        self.assertFalse(json.loads(err.getvalue())["ok"])


if __name__ == "__main__":
    unittest.main()
