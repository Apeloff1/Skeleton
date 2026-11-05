"""One-season coaching advisor replay, safety and CLI acceptance."""
import copy
import io
import json
import unittest
from contextlib import redirect_stdout, redirect_stderr

from skeleton.__main__ import main
from skeleton.game.gameplay.turn_combat import CombatSessionError
from skeleton.game.gameplay.combat_league_career import (
    advance_career, new_career, original_career,
)
from skeleton.game.gameplay.combat_league_career_advice import (
    advise_career, verify_advice,
)


class AdviceTests(unittest.TestCase):
    def setUp(self):
        self.saved = new_career(original_career())

    def test_advice_is_replayable_and_choice_is_real(self):
        result = advise_career(self.saved, "amber_guard")
        self.assertEqual(result["claim"], "one_season_replay_only")
        self.assertLessEqual(len(result["evaluated"]), 5)
        self.assertEqual(verify_advice(self.saved, result), result)
        self.assertEqual(
            advance_career(self.saved, result["recommended_choice"]),
            result["predicted_session"],
        )
        self.assertEqual(self.saved["state"]["next_season"], 0)

    def test_recommendation_never_claims_global_optimum(self):
        result = advise_career(self.saved, "canal_runner")
        self.assertEqual(result["season"], 0)
        self.assertEqual(result["claim"], "one_season_replay_only")
        self.assertTrue(all(len(item["score"]) == 3 for item in result["evaluated"]))

    def test_zero_tokens_only_allows_rest(self):
        source = original_career()
        source["training_tokens"] = 0
        result = advise_career(new_career(source), "amber_guard")
        self.assertEqual(result["recommended_choice"], {"kind": "rest"})
        self.assertEqual(len(result["evaluated"]), 1)

    def test_target_must_be_authored_and_session_active(self):
        with self.assertRaises(CombatSessionError):
            advise_career(self.saved, "not_an_entrant")
        finished = self.saved
        for _ in range(3):
            finished = advance_career(finished, {"kind": "rest"})
        with self.assertRaisesRegex(CombatSessionError, "terminal"):
            advise_career(finished, "amber_guard")

    def test_forged_choice_and_score_are_rejected(self):
        result = advise_career(self.saved, "amber_guard")
        for key, value in (
            ("recommended_choice", {"kind": "train", "entrant_id": "missing", "stat": "attack"}),
            ("predicted_state_digest", "0" * 64),
            ("claim", "globally_optimal"),
        ):
            forged = copy.deepcopy(result)
            forged[key] = value
            with self.assertRaises(CombatSessionError):
                verify_advice(self.saved, forged)

    def test_cli_demo_and_bad_session(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["combat-career-advice", "demo"]), 0)
        result = json.loads(out.getvalue())
        self.assertEqual(verify_advice(self.saved, result), result)
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(main(["combat-career-advice", "advise",
                                   "--session-json", '{"bad":true}',
                                   "--target-id", "amber_guard"]), 2)
        self.assertIn('"ok": false', err.getvalue())


if __name__ == "__main__":
    unittest.main()
