"""Scripted demo replays original source; real player demo remains fail-closed."""
from __future__ import annotations

import io
import json
import sys

from skeleton.__main__ import main
from skeleton.game.gameplay.scene_weather_interactive import cli
from skeleton.game.gameplay.scene_weather import (
    original_weather, simulate_weather, verify_weather,
)


def _events(output: str) -> list[dict]:
    return [json.loads(line) for line in output.splitlines() if line]


def test_scripted_demo_cannot_read_stdin_or_forge_terminal(monkeypatch, capsys):
    class NoInput:
        def readline(self, *_args):
            raise AssertionError("scripted demo must not read stdin")

    monkeypatch.setattr(sys, "stdin", NoInput())
    assert main(["scene-weather-play", "demo-script"]) == 0
    events = _events(capsys.readouterr().out)
    assert events[0]["event"] == "started"
    assert events[-1]["event"] == "checkpoint"
    assert events[-1]["reason"] == "terminal"
    assert events[-1]["session"]["state"]["phase"] == "won"
    terminal = next(item for item in reversed(events)
                    if item["event"] == "checkpoint")
    assert terminal["reason"] == "terminal"
    source, actions = original_weather()
    expected = simulate_weather(source, actions)
    assert expected["state"]["phase"] == "won"
    assert verify_weather(terminal["session"]) == expected
    assert terminal["state_digest"] == expected["state_digest"]


def test_interactive_demo_eof_fails_without_implicit_success(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert cli(["demo"]) == 2
    out = capsys.readouterr()
    events = _events(out.out)
    assert events[-1]["event"] == "checkpoint"
    assert events[-1]["reason"] == "input_eof"
    assert not any(event.get("event") == "terminal" for event in events)
    assert "error" in json.loads(out.err)
