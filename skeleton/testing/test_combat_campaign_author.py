"""Transactional combat campaign authoring, playable previews and integrity."""
from __future__ import annotations

import copy
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import unittest

from skeleton.game.gameplay.combat_campaign import normalize_campaign, original_campaign
from skeleton.game.gameplay.combat_campaign_author import (
    author_campaign, cli, demo_author, verify_author_report,
)
from skeleton.game.gameplay.combat_campaign_player import (
    import_player_campaign, verify_player_campaign,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError


class CampaignAuthorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = original_campaign()
        self.lease = dig(normalize_campaign(self.source))

    def test_demo_authors_and_plays_earned_reward(self) -> None:
        result = demo_author()
        self.assertEqual(result["after"]["encounters"][0]["reward"], 12)
        self.assertEqual(result["preview"]["state"]["phase"], "won")
        self.assertEqual(result["preview"]["state"]["currency"], 32)
        self.assertEqual(import_player_campaign(result["preview_bundle"]),
                         result["preview"])
        self.assertEqual(verify_author_report(result), result)

    def test_hero_stat_propagates_across_encounters(self) -> None:
        report = author_campaign(
            self.source, [{"kind": "set_actor_stat", "encounter_id": "reed_watch",
                           "actor_id": "scout", "field": "attack", "value": 6}],
            self.lease,
        )
        for entry in report["after"]["encounters"]:
            hero = next(a for a in entry["scenario"]["actors"] if a["id"] == "scout")
            self.assertEqual(hero["attack"], 6)
        self.assertEqual(report["preview"]["state"]["phase"], "active")
        self.assertIsNotNone(report["preview_board"])
        self.assertEqual(verify_player_campaign(report["preview"]),
                         report["preview"])
        self.assertEqual(verify_author_report(report), report)

    def test_reorder_turn_budget_and_opponent_stats_are_canonical(self) -> None:
        report = author_campaign(self.source, [
            {"kind": "reorder_encounters", "encounter_ids": ["tide_gate", "reed_watch"]},
            {"kind": "set_turn_limit", "encounter_id": "tide_gate", "turn_limit": 12},
            {"kind": "set_actor_stat", "encounter_id": "tide_gate",
             "actor_id": "mireling", "field": "defense", "value": 2},
        ], self.lease)
        self.assertEqual(report["after"]["encounters"][0]["scenario"]["encounter_id"],
                         "tide_gate")
        self.assertEqual(report["after"]["encounters"][0]["scenario"]["turn_limit"], 12)
        self.assertEqual(len(report["events"]), 3)
        self.assertEqual(verify_author_report(report), report)

    def test_source_unchanged_on_rejected_transaction(self) -> None:
        original = copy.deepcopy(self.source)
        for edits in (
            [{"kind": "set_reward", "encounter_id": "missing", "reward": 9}],
            [{"kind": "set_reward", "encounter_id": "reed_watch", "reward": 10}],
            [{"kind": "set_actor_stat", "encounter_id": "reed_watch",
              "actor_id": "warden", "field": "attack", "value": True}],
            [{"kind": "reorder_encounters", "encounter_ids": ["reed_watch"]}],
            [{"kind": "set_turn_limit", "encounter_id": "tide_gate", "turn_limit": 33}],
        ):
            with self.assertRaises(CombatSessionError):
                author_campaign(self.source, edits, self.lease)
            self.assertEqual(self.source, original)

    def test_stale_lease_invalid_batches_and_forged_reports(self) -> None:
        with self.assertRaisesRegex(CombatSessionError, "stale"):
            author_campaign(self.source, [
                {"kind": "set_reward", "encounter_id": "reed_watch", "reward": 12},
            ], "0" * 64)
        for edits in ([], [None], [{}], [None] * 17):
            with self.assertRaises(CombatSessionError):
                author_campaign(self.source, edits, self.lease)
        report = demo_author()
        forged = copy.deepcopy(report)
        forged["after"]["encounters"][0]["reward"] = 999
        forged["receipt"] = dig({k: v for k, v in forged.items() if k != "receipt"})
        with self.assertRaises(CombatSessionError):
            verify_author_report(forged)

    def test_top_level_cli_and_replayed_report(self) -> None:
        from skeleton.__main__ import main
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["combat-campaign-author", "demo"]), 0)
        report = json.loads(output.getvalue())
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(cli(["verify", "--report-json", json.dumps(report)]), 0)
        self.assertEqual(json.loads(output.getvalue()), report)
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(cli(["run", "--source-json", "{}",
                                  "--edits-json", "[]",
                                  "--expected-source-digest", self.lease]), 2)
        self.assertFalse(json.loads(err.getvalue())["ok"])


if __name__ == "__main__":
    unittest.main()
