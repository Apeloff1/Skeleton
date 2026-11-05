"""User-facing commission input, checkpoints and fail-closed command handling."""
from __future__ import annotations

import io
import json

import pytest

from skeleton.game.gameplay.scene_market_contract import (
    original_contract, simulate_contract, verify_contract,
)
from skeleton.game.gameplay.scene_market_contract_interactive import (
    cli, play_contract,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_interactive_complete_equals_canonical_market_contract():
    source, actions = original_contract()
    stream = io.StringIO()
    session = play_contract(
        source, input_stream=io.StringIO(
            "\n".join(json.dumps(action) for action in actions) + "\n"
        ), output_stream=stream, checkpoint_every=4,
    )
    assert session == simulate_contract(source, actions)
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert events[0]["event"] == "started"
    assert events[-1]["event"] == "terminal"
    assert events[-1]["phase"] == "won"
    assert verify_contract([e for e in events if e["event"] == "checkpoint"][-1]["session"]) == session


def test_eof_emits_recoverable_checkpoint():
    source, _ = original_contract()
    stream = io.StringIO()
    with pytest.raises(SceneTravelError, match="checkpoint emitted"):
        play_contract(source, input_stream=io.StringIO(""), output_stream=stream)
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert events[-1]["reason"] == "input_eof"
    assert verify_contract(events[-1]["session"]) == events[-1]["session"]


def test_three_invalid_actions_never_change_checkpoint():
    source, _ = original_contract()
    stream = io.StringIO()
    with pytest.raises(SceneTravelError, match="three invalid"):
        play_contract(source, input_stream=io.StringIO("buy fabricated\n" * 3),
                      output_stream=stream)
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len([e for e in events if e["event"] == "rejected"]) == 3
    assert events[-1]["reason"] == "invalid_commands"
    assert events[-1]["session"]["state"]["tick"] == 0


def test_interactive_source_binding_and_cli_demo(capsys):
    from skeleton.__main__ import main
    source, _ = original_contract()
    with pytest.raises(SceneTravelError, match="digest"):
        play_contract(source, expected_source_digest="0" * 64)
    assert main(["scene-market-contract-play", "demo"]) == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert events[-1]["event"] == "terminal"
    assert events[-1]["score"] == 25
    assert cli(["play", "--source-json", json.dumps(source),
                "--checkpoint-every", "0"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
