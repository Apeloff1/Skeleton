"""End-to-end merchant schedule interaction and acceptance regression."""
from __future__ import annotations

import copy
import io
import json

import pytest

from skeleton.game.gameplay.scene_market_hours import (
    new_hours, original_hours, simulate_hours,
)
from skeleton.game.gameplay.scene_market_hours_acceptance import (
    accept_hours, verify_hours_acceptance,
)
from skeleton.game.gameplay.scene_market_hours_interactive import (
    _commands, play_hours,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def _events(output: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in output.getvalue().splitlines()]


def test_interactive_demo_finishes_and_portable_checkpoint_matches():
    source, actions = original_hours()
    output = io.StringIO()
    terminal = play_hours(
        source, input_stream=io.StringIO(_commands(actions)),
        output_stream=output, checkpoint_every=3,
    )
    assert terminal == simulate_hours(source, actions)
    events = _events(output)
    assert events[-1]["event"] == "terminal"
    assert events[-1]["phase"] == "won"
    assert any(e["event"] == "checkpoint" and e["reason"] == "interval"
               for e in events)
    assert events[-2]["portable"]["session"] == terminal
    assert events[-2]["reason"] == "terminal"


def test_rejected_closed_market_keeps_checkpoint_and_recovers():
    source, actions = original_hours()
    source["windows"][0]["opens_at"] = 7
    checkpoint = simulate_hours(source, actions[:5])
    output = io.StringIO()
    with pytest.raises(SceneTravelError, match="input ended"):
        play_hours(
            session=checkpoint,
            input_stream=io.StringIO("buy copper_badge\n"),
            output_stream=output,
        )
    events = _events(output)
    assert any(e["event"] == "rejected" and "closed" in e["error"]
               for e in events)
    assert events[-1]["event"] == "checkpoint"
    assert events[-1]["session"] == checkpoint


def test_invalid_command_limit_preserves_restartable_save():
    source, actions = original_hours()
    checkpoint = simulate_hours(source, actions[:5])
    output = io.StringIO()
    with pytest.raises(SceneTravelError, match="three invalid"):
        play_hours(
            session=checkpoint,
            input_stream=io.StringIO("oops\noops\noops\n"),
            output_stream=output,
        )
    events = _events(output)
    assert events[-1]["reason"] == "invalid_commands"
    assert events[-1]["session"] == checkpoint


def test_source_pin_denies_rebinding_before_input():
    source, _ = original_hours()
    with pytest.raises(SceneTravelError, match="not trusted"):
        play_hours(
            source, expected_source_digest="0" * 64,
            input_stream=io.StringIO(""),
            output_stream=io.StringIO(),
        )


def test_acceptance_checks_editor_economy_and_replay():
    source, actions = original_hours()
    terminal = simulate_hours(source, actions)
    witness = accept_hours(terminal)
    assert witness["status"] == "accepted_offline_witness"
    assert witness["journal_length"] == len(actions)
    assert verify_hours_acceptance(terminal, copy.deepcopy(witness)) == witness
    forged = copy.deepcopy(witness)
    forged["merchant_purchases"]["gate_trader"] = 900
    with pytest.raises(SceneTravelError, match="witness"):
        verify_hours_acceptance(terminal, forged)


def test_acceptance_requires_real_victory_and_rejects_flags():
    source, actions = original_hours()
    partial = simulate_hours(source, actions[:5])
    with pytest.raises(SceneTravelError, match="victory"):
        accept_hours(partial)
    report = accept_hours(partial, require_victory=False)
    assert report["status"] == "incomplete"
    with pytest.raises(SceneTravelError, match="flags"):
        accept_hours(partial, require_victory=1)


def test_cli_dispatch_is_reachable(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-hours-play", "demo"]) == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert events[-1]["phase"] == "won"
    terminal = events[-2]["session"]
    assert main(["scene-market-hours-accept", "audit",
                 "--session-json", json.dumps(terminal)]) == 0
    witness = json.loads(capsys.readouterr().out)
    assert witness["status"] == "accepted_offline_witness"
