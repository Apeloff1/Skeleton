"""Interactive weather play: movement, collision, EOF and save replay."""
from __future__ import annotations

import io
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather import (
    new_session, original_weather_demo, resume_session, verify_session,
)
from skeleton.game.gameplay.scene_weather_interactive import (
    parse_weather_command, play_weather,
)


def _play(source, commands, **kwargs):
    output = io.StringIO()
    result = play_weather(source, input_stream=io.StringIO(commands),
                          output_stream=output, **kwargs)
    return result, [json.loads(line) for line in output.getvalue().splitlines()]


def test_player_can_collect_travel_and_win_with_replayable_terminal_save():
    source, actions = original_weather_demo()
    result, events = _play(
        source, "collect find_key\ntravel north\ntravel inside\n",
        checkpoint_every=2,
    )
    assert result["state"]["phase"] == "won"
    assert result == resume_session(new_session(source), actions)
    assert verify_session(result) == result
    assert events[0]["event"] == "started"
    assert any(event["event"] == "checkpoint"
               and event["reason"] == "interval" for event in events)
    assert events[-1]["event"] == "terminal"
    assert events[-1]["scene_id"] == "sanctuary"


def test_player_sees_weather_collision_and_can_wait_to_cross():
    source, _ = original_weather_demo()
    result, events = _play(
        source, "collect find_key\ntravel north\ntravel inside\n",
    )
    first_scene = next(event for event in events if event["event"] == "scene")
    north = next(item for item in first_scene["exits"] if item["id"] == "north")
    assert north["blocked_by_weather"] is True
    assert north["missing_item"] is True
    assert result["state"]["phase"] == "won"


def test_wait_command_is_real_weather_transition():
    source, actions = original_weather_demo()
    result, events = _play(
        source, "wait\ncollect find_key\ntravel north\ntravel inside\n",
    )
    assert result == resume_session(new_session(source), [
        {"kind": "wait"}, *actions,
    ])
    assert any(event["event"] == "accepted"
               and event["action"]["kind"] == "wait" for event in events)


def test_eof_emits_last_verified_checkpoint_without_fabricating_victory():
    source, _ = original_weather_demo()
    output = io.StringIO()
    with pytest.raises(SceneTravelError, match="checkpoint emitted"):
        play_weather(source, input_stream=io.StringIO("collect find_key\n"),
                     output_stream=output)
    events = [json.loads(line) for line in output.getvalue().splitlines()]
    checkpoint = events[-1]
    assert checkpoint["event"] == "checkpoint"
    assert checkpoint["reason"] == "input_eof"
    assert checkpoint["session"]["state"]["phase"] == "active"
    assert verify_session(checkpoint["session"]) == checkpoint["session"]


def test_three_invalid_commands_emit_checkpoint_and_never_advance():
    source, _ = original_weather_demo()
    output = io.StringIO()
    with pytest.raises(SceneTravelError, match="three invalid"):
        play_weather(source, input_stream=io.StringIO(
            "travel north\ntravel north\ntravel north\n"),
            output_stream=output)
    events = [json.loads(line) for line in output.getvalue().splitlines()]
    assert len([e for e in events if e["event"] == "rejected"]) == 3
    checkpoint = events[-1]
    assert checkpoint["session"] == new_session(source)


@pytest.mark.parametrize("command", [
    "", "wait now", "collect", "travel", "exit north",
    '{"kind":"wait","kind":"scene"}', '{"kind":"wait","x":1}',
])
def test_untrusted_commands_fail_closed(command):
    with pytest.raises(SceneTravelError):
        parse_weather_command(command)


def test_expected_digest_mismatch_rejected_before_play():
    source, _ = original_weather_demo()
    with pytest.raises(SceneTravelError, match="trusted digest"):
        play_weather(source, expected_source_digest="0" * 64,
                     input_stream=io.StringIO("wait\n"),
                     output_stream=io.StringIO())


def test_installed_cli_streams_playable_events_and_portable_save(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(
        "collect find_key\ntravel north\ntravel inside\n"))
    assert main(["scene-weather-play", "--demo", "--checkpoint-every", "1"]) == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    checkpoint = next(event for event in events
                      if event["event"] == "checkpoint"
                      and event["reason"] == "terminal")
    assert checkpoint["session"]["state"]["phase"] == "won"
    assert verify_session(checkpoint["session"]) == checkpoint["session"]
