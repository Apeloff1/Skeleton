"""Interactive survival player input, checkpoint recovery and CLI."""
from __future__ import annotations

import io
import json

import pytest

from skeleton.game.gameplay.scene_tile_survival import (
    original_survival, verify_survival,
)
from skeleton.game.gameplay.scene_tile_survival_interactive import (
    cli, parse_player_action, play_survival,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def _events(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_full_original_player_route_and_portable_terminal():
    source, _ = original_survival()
    reader = io.StringIO(
        "east\ncollect find_key\neast\neast\ntravel north\n"
        "rest\neast\neast\ntravel inside\n"
    )
    writer = io.StringIO()
    saved = play_survival(
        source=source, input_stream=reader, output_stream=writer,
        checkpoint_every=3,
    )
    assert saved["state"]["phase"] == "won"
    events = _events(writer)
    assert events[0]["event"] == "started"
    assert events[-1]["event"] == "terminal"
    assert events[-1]["bundle"]["state_digest"] == saved["state_digest"]
    assert len([e for e in events if e["event"] == "accepted"]) == 9
    assert any(e.get("reason") == "interval" for e in events)


def test_eof_checkpoint_resumes_without_state_loss():
    source, _ = original_survival()
    writer = io.StringIO()
    with pytest.raises(SceneTravelError, match="input ended"):
        play_survival(
            source=source, input_stream=io.StringIO("east\n"),
            output_stream=writer,
        )
    checkpoints = [
        event for event in _events(writer)
        if event["event"] == "checkpoint"
    ]
    assert checkpoints[-1]["reason"] == "input_eof"
    saved = verify_survival(checkpoints[-1]["session"])
    assert saved["state"]["tick"] == 1
    followup = io.StringIO(
        "collect find_key\neast\neast\ntravel north\n"
        "rest\neast\neast\ntravel inside\n"
    )
    resumed = play_survival(
        session=saved, expected_source_digest=saved["source_digest"],
        input_stream=followup, output_stream=io.StringIO(),
    )
    assert resumed["state"]["phase"] == "won"


def test_invalid_attempts_do_not_mutate_save():
    source, _ = original_survival()
    writer = io.StringIO()
    with pytest.raises(SceneTravelError, match="retries exhausted"):
        play_survival(
            source=source,
            input_stream=io.StringIO("teleport\nrest\nfly\n"),
            output_stream=writer,
        )
    events = _events(writer)
    assert len([e for e in events if e["event"] == "invalid"]) == 3
    checkpoint = events[-1]
    assert checkpoint["reason"] == "invalid_input_limit"
    assert checkpoint["session"]["state"]["tick"] == 0


def test_turn_budget_checkpoint():
    source, _ = original_survival()
    writer = io.StringIO()
    with pytest.raises(SceneTravelError, match="turn budget"):
        play_survival(
            source=source, input_stream=io.StringIO("east\n"),
            output_stream=writer, max_turns=1,
        )
    assert _events(writer)[-1]["reason"] == "turn_budget"


@pytest.mark.parametrize("raw", [
    "", "fly", "collect", "travel", "rest now",
    '{"kind":"tile","action":{"kind":"fly"}}',
    '{"kind":"rest","kind":"tile"}',
])
def test_bad_player_actions_rejected(raw):
    with pytest.raises(SceneTravelError):
        parse_player_action(raw)


def test_player_action_parsing_and_source_pin():
    assert parse_player_action("east") == {
        "kind": "tile", "action": {"kind": "move", "direction": "east"},
    }
    assert parse_player_action("rest") == {"kind": "rest"}
    source, _ = original_survival()
    with pytest.raises(SceneTravelError, match="trusted digest"):
        play_survival(
            source=source, expected_source_digest="0" * 64,
            input_stream=io.StringIO(), output_stream=io.StringIO(),
        )


def test_cli_demo_eof_fails_with_checkpoint(capsys, monkeypatch):
    from skeleton.__main__ import main
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert main(["scene-survival-play", "demo"]) == 2
    out = capsys.readouterr()
    assert '"event":"checkpoint"' in out.out
    assert '"error"' in out.err
    source, _ = original_survival()
    assert cli(["play", "--source-json", json.dumps(source),
                "--max-turns", "0"]) == 2
