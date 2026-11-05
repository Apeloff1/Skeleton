"""Bounded interactive weather session and resume acceptance."""
from __future__ import annotations

import copy
import io
import json
import unittest

from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather import (
    original_weather, simulate_weather, verify_weather,
)
from skeleton.game.gameplay.scene_weather_interactive import (
    parse_weather_command, play_weather,
)


class WeatherInteractiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source, self.actions = original_weather()

    def test_interactive_complete_matches_batch_reducer(self) -> None:
        reader = io.StringIO("".join(json.dumps(a) + "\n" for a in self.actions))
        writer = io.StringIO()
        final = play_weather(
            source=self.source, input_stream=reader, output_stream=writer,
            checkpoint_every=2)
        self.assertEqual(final, simulate_weather(self.source, self.actions))
        events = [json.loads(line) for line in writer.getvalue().splitlines()]
        self.assertEqual(events[0]["event"], "started")
        self.assertEqual(events[-1]["reason"], "terminal")
        self.assertEqual(events[-1]["session"], final)
        self.assertTrue(any(e["event"] == "weather" for e in events))
        self.assertEqual(
            len([e for e in events if e["event"] == "accepted"]),
            len(self.actions))

    def test_eof_emits_verifiable_checkpoint(self) -> None:
        writer = io.StringIO()
        with self.assertRaisesRegex(SceneTravelError, "input ended"):
            play_weather(
                source=self.source, input_stream=io.StringIO(""),
                output_stream=writer)
        events = [json.loads(line) for line in writer.getvalue().splitlines()]
        self.assertEqual(events[-1]["reason"], "input_eof")
        self.assertEqual(verify_weather(events[-1]["session"]), events[-1]["session"])

    def test_retries_do_not_advance_game_state(self) -> None:
        writer = io.StringIO()
        with self.assertRaisesRegex(SceneTravelError, "retry budget"):
            play_weather(
                source=self.source,
                input_stream=io.StringIO("equip unearned\nunequip\nmove diagonal\n"),
                output_stream=writer)
        events = [json.loads(line) for line in writer.getvalue().splitlines()]
        self.assertEqual(
            [e["attempt"] for e in events if e["event"] == "rejected"],
            [1, 2, 3])
        self.assertEqual(events[-1]["session"]["state"]["tick"], 0)

    def test_resume_requires_trusted_source_digest(self) -> None:
        saved = simulate_weather(self.source, self.actions[:3])
        writer = io.StringIO()
        reader = io.StringIO("".join(
            json.dumps(a) + "\n" for a in self.actions[3:]))
        final = play_weather(
            session=saved, expected_source_digest=saved["source_digest"],
            input_stream=reader, output_stream=writer)
        self.assertEqual(final, simulate_weather(self.source, self.actions))
        with self.assertRaisesRegex(SceneTravelError, "trusted input"):
            play_weather(
                session=saved, expected_source_digest="0" * 64,
                input_stream=io.StringIO(""),
                output_stream=io.StringIO())

    def test_text_commands_and_input_budget(self) -> None:
        self.assertEqual(parse_weather_command("equip stormcloak"),
                         {"kind": "equip", "gear_id": "stormcloak"})
        self.assertEqual(parse_weather_command("rest"),
                         {"kind": "survival", "action": {"kind": "rest"}})
        with self.assertRaises(SceneTravelError):
            parse_weather_command("x" * 9000)
        with self.assertRaises(SceneTravelError):
            parse_weather_command("move diagonal extra")

    def test_checkpoint_tampering_is_rejected(self) -> None:
        saved = simulate_weather(self.source, self.actions[:2])
        forged = copy.deepcopy(saved)
        forged["state"]["stamina"] += 1
        with self.assertRaises(SceneTravelError):
            play_weather(
                session=forged, input_stream=io.StringIO(""),
                output_stream=io.StringIO())


if __name__ == "__main__":
    unittest.main()
