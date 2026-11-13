"""Integrated weather gameplay acceptance, stream budgets and forgery holds."""
from __future__ import annotations

import copy
import unittest

from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather import original_weather
from skeleton.game.gameplay.scene_weather_acceptance import (
    MAX_TRANSCRIPT_BYTES, _CappedTranscript, accept_weather,
    verify_weather_acceptance,
)


class WeatherAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source, self.actions = original_weather()

    def test_original_playable_vertical_round_trip(self) -> None:
        result = accept_weather(self.source, self.actions)
        self.assertEqual(result["status"], "playable_verified")
        self.assertEqual(result["action_count"], len(self.actions))
        self.assertEqual(verify_weather_acceptance(result, self.source), result)
        self.assertGreaterEqual(result["checkpoint_count"], 1)
        self.assertEqual(len(result["portable_checksum"]), 64)

    def test_nonwinning_prefix_not_accepted(self) -> None:
        with self.assertRaisesRegex(SceneTravelError, "requires a playable victory"):
            accept_weather(self.source, self.actions[:1])

    def test_action_budget_rejects_boolean_and_oversize(self) -> None:
        for actions in ([], "bad", None, [None] * 33):
            with self.subTest(actions=str(actions)[:30]):
                with self.assertRaises(SceneTravelError):
                    accept_weather(self.source, actions)

    def test_source_and_receipt_tampering_fail_closed(self) -> None:
        proof = accept_weather(self.source, self.actions)
        changed = copy.deepcopy(self.source)
        changed["max_stamina"] += 1
        with self.assertRaises(SceneTravelError):
            verify_weather_acceptance(proof, changed)
        forged = copy.deepcopy(proof)
        forged["action_count"] += 1
        with self.assertRaises(SceneTravelError):
            verify_weather_acceptance(forged, self.source)
        forged = copy.deepcopy(proof)
        forged["checksum"] = "0" * 64
        with self.assertRaisesRegex(SceneTravelError, "checksum"):
            verify_weather_acceptance(forged, self.source)

    def test_interactive_transcript_is_bounded(self) -> None:
        stream = _CappedTranscript()
        stream.write("x" * MAX_TRANSCRIPT_BYTES)
        with self.assertRaisesRegex(SceneTravelError, "size budget"):
            stream.write("x")


if __name__ == "__main__":
    unittest.main()
