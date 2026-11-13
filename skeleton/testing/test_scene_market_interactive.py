"""Offline market interactive play, source custody and safe fallback."""
from __future__ import annotations

import io
import json

import pytest

from skeleton.game.gameplay.scene_market import (
    original_market, simulate_market, verify_market,
)
from skeleton.game.gameplay.scene_market_interactive import (
    cli, parse_market_command, play_market,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def _commands(actions):
    commands = []
    for action in actions:
        if action["kind"] == "tile":
            nested = action["action"]
            field = {"move": "direction", "collect": "pickup_id",
                     "travel": "exit_id"}[nested["kind"]]
            commands.append(nested["kind"] + " " + nested[field])
        else:
            field = {"buy": "offer_id", "craft": "recipe_id",
                     "deliver": "delivery_id"}[action["kind"]]
            commands.append(action["kind"] + " " + action[field])
    return "\n".join(commands) + "\n"


def test_interactive_market_full_delivery_and_checkpoint():
    source, actions = original_market()
    writer = io.StringIO()
    result = play_market(
        source, input_stream=io.StringIO(_commands(actions)),
        output_stream=writer, checkpoint_every=3,
    )
    assert result == simulate_market(source, actions)
    events = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert events[0]["event"] == "started"
    assert events[-1]["event"] == "terminal"
    assert events[-1]["phase"] == "won"
    assert events[-1]["reputation"] == 5
    checkpoints = [e for e in events if e["event"] == "checkpoint"]
    assert any(e["reason"] == "interval" for e in checkpoints)
    assert checkpoints[-1]["reason"] == "terminal"
    assert verify_market(checkpoints[-1]["session"]) == result


def test_eof_emits_replayable_checkpoint():
    source, actions = original_market()
    writer = io.StringIO()
    with pytest.raises(SceneTravelError, match="input ended"):
        play_market(source, input_stream=io.StringIO(_commands(actions[:4])),
                    output_stream=writer)
    events = [json.loads(line) for line in writer.getvalue().splitlines()]
    checkpoint = events[-1]
    assert checkpoint["event"] == "checkpoint"
    assert checkpoint["reason"] == "input_eof"
    assert verify_market(checkpoint["session"]) == (
        simulate_market(source, actions[:4])
    )


def test_three_bad_commands_preserve_last_valid_state():
    source, _ = original_market()
    writer = io.StringIO()
    with pytest.raises(SceneTravelError, match="three invalid"):
        play_market(source, input_stream=io.StringIO("move west\nbuy forged\n{}\n"),
                    output_stream=writer)
    events = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert len([e for e in events if e["event"] == "rejected"]) == 3
    assert events[-1]["reason"] == "invalid_commands"
    assert events[-1]["session"]["state"]["tick"] == 0


def test_resume_checkpoint_and_source_lease():
    source, actions = original_market()
    partial = simulate_market(source, actions[:5])
    writer = io.StringIO()
    resumed = play_market(
        session=partial, expected_source_digest=partial["source_digest"],
        input_stream=io.StringIO(_commands(actions[5:])),
        output_stream=writer,
    )
    assert resumed == simulate_market(source, actions)
    with pytest.raises(SceneTravelError, match="digest"):
        play_market(session=partial, expected_source_digest="0" * 64,
                    input_stream=io.StringIO(), output_stream=io.StringIO())


@pytest.mark.parametrize("command", [
    "move teleport", "buy", "delete /tmp", '{"kind":"buy","kind":"deliver"}',
    '{"kind":"buy","offer_id":NaN}', " " * 20,
])
def test_bad_command_rejected(command):
    if command == "move teleport":
        assert parse_market_command(command)["action"]["direction"] == "teleport"
    else:
        with pytest.raises(SceneTravelError):
            parse_market_command(command)


def test_main_cli_demo_user_reachable(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-play", "demo"]) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert lines[-1]["event"] == "terminal"
    assert lines[-1]["phase"] == "won"
    assert cli(["play", "--source-json", '{"x":1,"x":2}']) == 2
    assert "error" in json.loads(capsys.readouterr().err)
