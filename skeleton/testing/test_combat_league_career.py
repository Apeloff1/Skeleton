"""Source-bound playable coaching career regression tests."""
import copy
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from skeleton.__main__ import main
from skeleton.game.gameplay.turn_combat import CombatSessionError
from skeleton.game.gameplay.combat_league_career import (
    advance_career, career_board, export_career, finish_career,
    import_career, new_career, normalize_career, original_career,
    verify_career,
)


class CareerTests(unittest.TestCase):
    def setUp(self):
        self.source = original_career()

    def test_original_source_is_playable_and_replayable(self):
        choices = [
            {"kind": "train", "entrant_id": "amber_guard", "stat": "attack"},
            {"kind": "rest"},
            {"kind": "train", "entrant_id": "canal_runner", "stat": "speed"},
        ]
        completed = finish_career(self.source, choices)
        self.assertEqual(completed["state"]["phase"], "won")
        self.assertEqual(completed["state"]["next_season"], 3)
        self.assertEqual(completed["state"]["tokens_remaining"], 0)
        self.assertEqual(verify_career(completed), completed)
        self.assertEqual(import_career(export_career(completed)), completed)
        self.assertEqual(finish_career(self.source, choices), completed)

    def test_resume_is_identical_to_full_run(self):
        choices = [{"kind": "rest"}, {"kind": "rest"}, {"kind": "rest"}]
        one = advance_career(new_career(self.source), choices[0])
        two = advance_career(one, choices[1])
        final = finish_career(self.source, choices[2:], resume=two)
        self.assertEqual(final, finish_career(self.source, choices))
        self.assertEqual(career_board(final)["seasons_played"], 3)

    def test_exhausted_training_budget_fails_closed(self):
        first = advance_career(new_career(self.source), {
            "kind": "train", "entrant_id": "amber_guard", "stat": "attack",
        })
        second = advance_career(first, {
            "kind": "train", "entrant_id": "amber_guard", "stat": "attack",
        })
        with self.assertRaisesRegex(CombatSessionError, "tokens"):
            advance_career(second, {
                "kind": "train", "entrant_id": "amber_guard", "stat": "attack",
            })
        self.assertEqual(second["state"]["next_season"], 2)

    def test_invalid_choice_does_not_change_input(self):
        initial = new_career(self.source)
        before = copy.deepcopy(initial)
        bad = (
            {"kind": "train", "entrant_id": "missing", "stat": "attack"},
            {"kind": "train", "entrant_id": "amber_guard", "stat": "magic"},
            {"kind": "rest", "unexpected": 1}, {"kind": "train", "stat": "speed"},
            {"kind": "train", "entrant_id": "amber_guard", "stat": True},
            {"kind": "rest", "entrant_id": "amber_guard"}, {"kind": "unknown"},
        )
        for choice in bad:
            with self.subTest(choice=choice), self.assertRaises(CombatSessionError):
                advance_career(initial, choice)
            self.assertEqual(initial, before)

    def test_save_tampering_and_lineage_fail(self):
        saved = advance_career(new_career(self.source), {"kind": "rest"})
        cases = []
        forged = copy.deepcopy(saved)
        forged["state"]["wins"]["amber_guard"] += 100
        cases.append(forged)
        forged = copy.deepcopy(saved)
        forged["state"]["season_journal"][0]["winner"] = "unknown"
        cases.append(forged)
        forged = copy.deepcopy(saved)
        forged["save"]["parent_save_digest"] = "0" * 64
        cases.append(forged)
        forged = copy.deepcopy(saved)
        forged["state"]["season_journal"][0]["league"]["state"]["points"]["amber_guard"] += 1
        cases.append(forged)
        for case in cases:
            with self.subTest(case=case["state"]["next_season"]):
                with self.assertRaises(CombatSessionError):
                    verify_career(case)

    def test_invalid_source_and_boundaries(self):
        for key, value in (("seasons", 0), ("seasons", 5), ("seasons", True),
                           ("training_tokens", 5), ("career_id", "x" * 49),
                           ("unexpected", "extra")):
            bad = copy.deepcopy(self.source)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(CombatSessionError):
                normalize_career(bad)
        capped = copy.deepcopy(self.source)
        capped["league"]["entrants"][0]["attack"] = 1000
        initial = new_career(capped)
        with self.assertRaisesRegex(CombatSessionError, "stat bound"):
            advance_career(initial, {"kind": "train", "entrant_id": "amber_guard", "stat": "attack"})

    def test_terminal_and_cross_source_resume_rejected(self):
        complete = finish_career(self.source, [{"kind": "rest"}] * 3)
        with self.assertRaises(CombatSessionError):
            advance_career(complete, {"kind": "rest"})
        modified = copy.deepcopy(self.source)
        modified["career_id"] = "different"
        with self.assertRaisesRegex(CombatSessionError, "source mismatch"):
            finish_career(modified, [], resume=complete)

    def test_export_tamper_and_cli(self):
        saved = new_career(self.source)
        bundle = export_career(saved)
        bundle["checksum"] = "0" * 64
        with self.assertRaises(CombatSessionError):
            import_career(bundle)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["combat-career", "new", "--source-json",
                                   json.dumps(self.source)]), 0)
        self.assertEqual(verify_career(json.loads(out.getvalue())), saved)
        error = io.StringIO()
        with redirect_stderr(error):
            self.assertEqual(main(["combat-career", "new", "--source-json",
                                   '{"bad":true}']), 2)
        self.assertIn('"ok": false', error.getvalue())


if __name__ == "__main__":
    unittest.main()
