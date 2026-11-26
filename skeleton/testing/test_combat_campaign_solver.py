"""Canonical player campaign route search, witness and CLI contracts."""
from __future__ import annotations

import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import unittest

from skeleton.game.gameplay.combat_campaign import original_campaign
from skeleton.game.gameplay.combat_campaign_player import (
    demo_player_campaign, export_player_campaign, import_player_campaign,
    new_player_campaign, resume_player_campaign,
)
from skeleton.game.gameplay.combat_campaign_solver import (
    cli, solve_campaign, verify_campaign_route,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError


class CampaignRouteTests(unittest.TestCase):
    def test_original_source_replays_earned_victory_and_export(self) -> None:
        source = original_campaign()
        report = solve_campaign(source=source)
        self.assertEqual(report["status"], "solved")
        self.assertGreater(len(report["actions"]), 0)
        self.assertEqual(verify_campaign_route(report), report)
        final = resume_player_campaign(new_player_campaign(source), report["actions"])
        self.assertEqual(final, report["terminal_session"])
        self.assertEqual(final["state"]["phase"], "won")
        self.assertEqual(final["state"]["currency"], 30)
        self.assertEqual(import_player_campaign(report["portable_bundle"]), final)

    def test_resume_from_replayed_player_checkpoint(self) -> None:
        demo = demo_player_campaign()
        checkpoint = resume_player_campaign(
            new_player_campaign(original_campaign()), [demo["journal"][0]["action"]])
        report = solve_campaign(session=checkpoint)
        self.assertEqual(report["start_session"], checkpoint)
        self.assertEqual(verify_campaign_route(report), report)
        if report["status"] == "solved":
            self.assertEqual(
                resume_player_campaign(checkpoint, report["actions"]),
                report["terminal_session"],
            )

    def test_state_and_depth_budget_are_inconclusive(self) -> None:
        state = solve_campaign(source=original_campaign(), max_states=1)
        self.assertEqual(state["status"], "inconclusive")
        self.assertIn("state_budget", state["incomplete_reasons"])
        self.assertIsNone(state["portable_bundle"])
        self.assertEqual(verify_campaign_route(state), state)
        depth = solve_campaign(source=original_campaign(), max_depth=1)
        self.assertEqual(depth["status"], "inconclusive")
        self.assertIn("depth_budget", depth["incomplete_reasons"])

    def test_terminal_checkpoint_does_not_mint_rewards(self) -> None:
        final = demo_player_campaign()
        report = solve_campaign(session=final)
        self.assertEqual(report["status"], "solved")
        self.assertEqual(report["actions"], [])
        self.assertEqual(report["terminal_session"], final)
        self.assertEqual(report["portable_bundle"], export_player_campaign(final))

    def test_tampering_rejected_even_after_rehash(self) -> None:
        report = solve_campaign(source=original_campaign())
        with self.assertRaisesRegex(CombatSessionError, "stale"):
            verify_campaign_route(report, expected_source_digest="0" * 64)
        for change in (
            lambda x: x["terminal_session"]["state"].update(currency=900),
            lambda x: x["actions"][0].update(kind="rest"),
            lambda x: x["limits"].update(max_frontier=999),
        ):
            forged = copy.deepcopy(report)
            change(forged)
            forged["receipt"] = dig({k: v for k, v in forged.items()
                                     if k != "receipt"})
            with self.assertRaises(CombatSessionError):
                verify_campaign_route(forged)

    def test_bad_limits_and_forged_checkpoint_fail_closed(self) -> None:
        source = original_campaign()
        for kwargs in ({"max_states": True}, {"max_states": 0},
                       {"max_states": 257}, {"max_depth": 17},
                       {"max_choices": 0}, {"max_choices": False}):
            with self.assertRaises(CombatSessionError):
                solve_campaign(source=source, **kwargs)
        with self.assertRaises(CombatSessionError):
            solve_campaign(source=source, session=new_player_campaign(source))
        with self.assertRaises(CombatSessionError):
            solve_campaign()
        forged = new_player_campaign(source)
        forged["state"]["currency"] = 900
        with self.assertRaises(CombatSessionError):
            solve_campaign(session=forged)

    def test_top_level_cli_demo_verify_and_invalid_source(self) -> None:
        from skeleton.__main__ import main
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["combat-campaign-solve", "demo"]), 0)
        report = json.loads(out.getvalue())
        self.assertEqual(report["status"], "solved")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli(["verify", "--report-json", json.dumps(report),
                                  "--expected-source-digest",
                                  report["source_digest"]]), 0)
        self.assertEqual(json.loads(out.getvalue()), report)
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(cli(["solve", "--source-json", "{}"]), 2)
        self.assertFalse(json.loads(err.getvalue())["ok"])


if __name__ == "__main__":
    unittest.main()
