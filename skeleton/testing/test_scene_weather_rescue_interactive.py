"""Accessible rescue CLI, source identity, replay and EOF checkpoints."""
from __future__ import annotations

import io
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather_rescue import (
    original_rescue, play_rescue, verify_rescue,
)
from skeleton.game.gameplay.scene_weather_rescue_interactive import (
    parse_rescue_command, play_rescue_interactive,
)


def _play(commands, *, session=None, checkpoint_every=4):
    writer = io.StringIO()
    source, _ = original_rescue()
    try:
        result = play_rescue_interactive(
            source if session is None else None, session=session,
            input_stream=io.StringIO(commands), output_stream=writer,
            checkpoint_every=checkpoint_every,
        )
    except SceneTravelError:
        result = None
    events = [json.loads(line) for line in writer.getvalue().splitlines()]
    return result, events


def test_human_rescue_commands_reach_real_shelter_and_earned_reward():
    commands = "rescue canal_medic\ncollect find_key\ntravel north\nshelter canal_medic\n"
    result, events = _play(commands)
    assert result is not None
    assert result["state"]["phase"] == "won"
    assert result["state"]["earned"] == 25
    assert verify_rescue(result) == result
    assert events[-1]["event"] == "terminal"
    assert events[-1]["earned"] == 25
    assert events[1]["available_rescue_commands"] == ["rescue canal_medic"]


def test_eof_and_resume_preserve_exact_canonical_checkpoint():
    result, events = _play("rescue canal_medic\ncollect find_key\n")
    assert result is None
    checkpoint = events[-1]
    assert checkpoint["event"] == "checkpoint"
    assert checkpoint["reason"] == "input_eof"
    saved = checkpoint["session"]
    assert verify_rescue(saved) == saved
    resumed, _ = _play("travel north\nshelter canal_medic\n", session=saved)
    assert resumed is not None
    source, actions = original_rescue()
    assert resumed == play_rescue(source, actions)


def test_invalid_commands_never_advance_or_grant_rewards():
    result, events = _play("shelter canal_medic\nteleport anywhere\nrescue forged\n")
    assert result is None
    checkpoint = events[-1]
    assert checkpoint["reason"] == "invalid_commands"
    assert checkpoint["session"]["state"]["tick"] == 0
    assert checkpoint["session"]["state"]["earned"] == 0
    assert verify_rescue(checkpoint["session"]) == checkpoint["session"]


@pytest.mark.parametrize("line", [
    "rescue", "shelter", "collect", "teleport north",
    '{"kind":"rescue","npc_id":"a","npc_id":"b"}',
    '{"kind":"weather","action":{"kind":"teleport"}}',
])
def test_parser_rejects_malformed_or_unsafe_commands(line):
    with pytest.raises(SceneTravelError):
        parse_rescue_command(line)


def test_source_digest_mismatch_rejected_before_input():
    source, _ = original_rescue()
    with pytest.raises(SceneTravelError, match="trusted digest"):
        play_rescue_interactive(
            source, expected_source_digest="0" * 64,
            input_stream=io.StringIO("rescue canal_medic\n"),
            output_stream=io.StringIO(),
        )


def test_installed_cli_reaches_original_gameplay_and_checkpoint(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(
        "rescue canal_medic\ncollect find_key\ntravel north\nshelter canal_medic\n",
    ))
    assert main(["scene-weather-rescue-play", "--demo"]) == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert events[-1]["event"] == "terminal"
    assert events[-1]["earned"] == 25
