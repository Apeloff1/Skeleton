"""Canonical league round-robin acceptance, recovery and hostile input tests."""
import copy
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from skeleton.__main__ import main
from skeleton.game.gameplay.turn_combat import CombatSessionError
from skeleton.game.gameplay.combat_league import (
    _json, _pairings, advance_league, export_league, finish_league,
    import_league, new_league, normalize_league, original_league,
    standings, verify_league,
)


class CombatLeagueTests(unittest.TestCase):
    def setUp(self):
        self.source = original_league()

    def test_three_rounds_are_canonical_and_all_entrants_play(self):
        result = finish_league(self.source)
        self.assertEqual(result["state"]["next_round"], 3)
        self.assertEqual(len(result["state"]["rounds"]), 3)
        self.assertEqual(verify_league(result), result)
        for round_index in range(3):
            groups = _pairings(normalize_league(self.source), round_index)
            names = [e["id"] for group in groups for e in group["entrants"]]
            self.assertEqual(len(names), 8)
            self.assertEqual(len(set(names)), 8)
            for tournament in result["state"]["rounds"][round_index]["brackets"]:
                self.assertEqual(tournament["state"]["phase"] in ("won", "draw"), True)
        table = standings(result)
        self.assertEqual(sum(row["points"] for row in table["ranking"]),
                         sum(result["state"]["points"].values()))
        self.assertEqual(table["ranking"],
                         sorted(table["ranking"], key=lambda r: (-r["points"], r["entrant_id"])))

    def test_schedule_changes_opponent_groups_each_round(self):
        spec = normalize_league(self.source)
        partitions = []
        for round_index in range(spec["rounds"]):
            groups = _pairings(spec, round_index)
            first = frozenset(e["id"] for e in groups[0]["entrants"])
            second = frozenset(e["id"] for e in groups[1]["entrants"])
            self.assertFalse(first & second)
            self.assertEqual(len(first | second), 8)
            partitions.append(frozenset((first, second)))
        self.assertEqual(len(set(partitions)), spec["rounds"])

    def test_derived_tournament_id_length_is_bounded(self):
        changed = copy.deepcopy(self.source)
        changed["league_id"] = "a" * 49
        with self.assertRaisesRegex(CombatSessionError, "too long"):
            normalize_league(changed)

    def test_resume_matches_one_pass_and_portable_export(self):
        initial = new_league(self.source)
        first = advance_league(initial)
        second = advance_league(first)
        complete = finish_league(self.source, resume=second)
        self.assertEqual(complete, finish_league(self.source))
        self.assertEqual(import_league(export_league(complete)), complete)
        self.assertEqual(first, advance_league(initial))

    def test_forged_points_match_winner_and_parent_save_fail(self):
        complete = finish_league(self.source)
        cases = []
        changed = copy.deepcopy(complete)
        changed["state"]["points"][next(iter(changed["state"]["points"]))] += 10
        cases.append(changed)
        changed = copy.deepcopy(complete)
        changed["state"]["rounds"][0]["points_awarded"]["amber_guard"] += 5
        cases.append(changed)
        changed = copy.deepcopy(complete)
        changed["state"]["rounds"][0]["brackets"][0]["state"]["matches"][0]["winner"] = "fake"
        cases.append(changed)
        changed = copy.deepcopy(complete)
        changed["save"]["parent_save_digest"] = "0" * 64
        cases.append(changed)
        for item in cases:
            with self.subTest(item=item["state"]["next_round"]):
                with self.assertRaises(CombatSessionError):
                    verify_league(item)

    def test_invalid_source_and_duplicate_entrant_fail_closed(self):
        for key, value in (("rounds", 5), ("rounds", True),
                           ("match_turn_limit", 0), ("unexpected", "yes")):
            changed = copy.deepcopy(self.source)
            changed[key] = value
            with self.assertRaises(CombatSessionError):
                normalize_league(changed)
        changed = copy.deepcopy(self.source)
        changed["entrants"][4]["id"] = changed["entrants"][0]["id"]
        with self.assertRaises(CombatSessionError):
            normalize_league(changed)

    def test_resume_source_mismatch_and_terminal_round(self):
        finished = finish_league(self.source)
        with self.assertRaises(CombatSessionError):
            advance_league(finished)
        changed = copy.deepcopy(self.source)
        changed["entrants"][0]["attack"] += 1
        with self.assertRaisesRegex(CombatSessionError, "source mismatch"):
            finish_league(changed, resume=finished)

    def test_bundle_and_hostile_json_rejected(self):
        bundle = export_league(new_league(self.source))
        bundle["checksum"] = "0" * 64
        with self.assertRaises(CombatSessionError):
            import_league(bundle)
        for text in ('{"a":1,"a":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(CombatSessionError):
                _json(text, "hostile")
        with self.assertRaises(CombatSessionError):
            _json("x" * (2 * 1024 * 1024 + 1), "hostile")

    def test_main_cli_demo_and_invalid_source(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["combat-league", "demo"]), 0)
        self.assertEqual(verify_league(json.loads(output.getvalue())),
                         json.loads(output.getvalue()))
        error = io.StringIO()
        with redirect_stderr(error):
            code = main(["combat-league", "simulate",
                         "--source-json", '{"invalid":true}'])
        self.assertEqual(code, 2)
        self.assertIn('"ok": false', error.getvalue())


if __name__ == "__main__":
    unittest.main()
