"""Weather route and board regression: legal actions, replay and forged proofs."""
from __future__ import annotations

import copy
import unittest

from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather import (
    _advance, export_weather, new_weather, original_weather, resume_weather,
    simulate_weather,
)
from skeleton.game.gameplay.scene_weather_board import weather_board
from skeleton.game.gameplay.scene_weather_route import (
    legal_weather_actions, solve_weather_route, verify_weather_route,
)


class WeatherRouteBoardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source, self.actions = original_weather()

    def test_board_exposes_only_canonical_legal_actions(self) -> None:
        session = new_weather(self.source)
        board = weather_board(session)
        self.assertEqual(board["state_digest"], session["state_digest"])
        self.assertEqual(board["forecast_next"]["kind"], "rain")
        self.assertFalse(board["choices_truncated"])
        self.assertNotIn({"kind": "equip", "gear_id": "stormcloak"},
                         board["legal_actions"])
        for action in board["legal_actions"]:
            self.assertEqual(_advance(session, action)["state"]["tick"], 1)

    def test_earned_gear_appears_after_collection(self) -> None:
        earned = simulate_weather(self.source, self.actions[:2])
        board = weather_board(earned)
        self.assertIn({"kind": "equip", "gear_id": "stormcloak"},
                      board["legal_actions"])
        self.assertEqual(board["owned_gear"], ["stormcloak"])

    def test_terminal_board_never_suggests_actions(self) -> None:
        won = simulate_weather(self.source, self.actions)
        board = weather_board(won)
        self.assertEqual(board["phase"], "won")
        self.assertEqual(board["legal_actions"], [])
        self.assertIsNone(board["forecast_next"])
        proof = solve_weather_route(session=won, max_states=1, max_depth=1)
        self.assertEqual(proof["status"], "proven_win")
        self.assertEqual(verify_weather_route(proof, session=won), won)

    def test_nonwinning_budgets_are_inconclusive(self) -> None:
        proof = solve_weather_route(self.source, max_states=1, max_depth=1)
        self.assertEqual(proof["status"], "inconclusive")
        self.assertEqual(proof["actions"], [])
        with self.assertRaises(SceneTravelError):
            verify_weather_route(proof, source=self.source)

    def test_replay_witness_and_checksum_reject_forgery(self) -> None:
        won = simulate_weather(self.source, self.actions)
        proof = solve_weather_route(session=won, max_states=1, max_depth=1)
        forged = copy.deepcopy(proof)
        forged["portable_checksum"] = "0" * 64
        with self.assertRaises(SceneTravelError):
            verify_weather_route(forged, session=won)
        forged = copy.deepcopy(proof)
        forged["actions"] = [{"kind": "unequip"}]
        with self.assertRaises(SceneTravelError):
            verify_weather_route(forged, session=won)

    def test_stale_checkpoint_rejected_and_input_budgets_fail_closed(self) -> None:
        start = new_weather(self.source)
        altered = copy.deepcopy(start)
        altered["state"]["stamina"] = 99
        with self.assertRaises(SceneTravelError):
            weather_board(altered)
        for bad in (0, True, 65):
            with self.assertRaises(SceneTravelError):
                weather_board(start, max_choices=bad)
        for bad in (0, True, 1025):
            with self.assertRaises(SceneTravelError):
                solve_weather_route(self.source, max_states=bad)
        for bad in (0, True, 49):
            with self.assertRaises(SceneTravelError):
                solve_weather_route(self.source, max_depth=bad)

    def test_resume_legal_actions_replay_and_export(self) -> None:
        initial = new_weather(self.source)
        first = legal_weather_actions(initial)[0]
        resumed = resume_weather(initial, [first])
        self.assertEqual(resumed["state"]["tick"], 1)
        self.assertEqual(export_weather(resumed)["state_digest"],
                         resumed["state_digest"])


if __name__ == "__main__":
    unittest.main()
