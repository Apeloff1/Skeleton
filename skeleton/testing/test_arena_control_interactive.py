"""Interactive capture game: player authority, AI, EOF, resume and CLI."""
from __future__ import annotations

import io
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.arena_control import (
    original_control, verify_control,
)
from skeleton.game.gameplay.arena_control_interactive import (
    MAX_INPUT_BYTES, play_interactive,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def _run(text: str, *, resume=None, max_inputs=64):
    output = io.StringIO()
    result = play_interactive(
        original_control(), "wayfarers", resume=resume,
        input_stream=io.StringIO(text), output_stream=output,
        max_inputs=max_inputs,
    )
    events = [json.loads(line) for line in output.getvalue().splitlines()]
    return result, events


def test_real_player_commands_opponent_ai_and_capture_victory():
    commands = [
        {"kind": "move", "actor_id": "scout", "direction": "east"},
        {"kind": "guard", "actor_id": "scout"},
    ]
    result, events = _run("\n".join(json.dumps(c) for c in commands) + "\n")
    assert result["status"] == "completed"
    assert result["session"]["state"]["winner"] == "wayfarers"
    assert verify_control(result["session"]) == result["session"]
    assert [event["type"] for event in events] == [
        "player_turn", "player_action", "opponent_action",
        "player_turn", "player_action", "checkpoint",
    ]
    assert events[0]["legal_actions"]
    assert events[-1]["session_digest"] == result["session_digest"]


def test_eof_preserves_checkpoint_and_resume_is_identical():
    first, events = _run(json.dumps({
        "kind": "move", "actor_id": "scout", "direction": "east",
    }) + "\n")
    assert first["status"] == "checkpoint"
    assert first["reason"] == "input_eof"
    assert first["session"]["state"]["tick"] == 2
    second, _ = _run(json.dumps({
        "kind": "guard", "actor_id": "scout",
    }) + "\n", resume=first["session"])
    assert second["status"] == "completed"
    assert verify_control(second["session"]) == second["session"]


@pytest.mark.parametrize("input_text,reason", [
    ('{"kind":"guard","actor_id":"warden"}\n', "does not own"),
    ('{"kind":"teleport","actor_id":"scout"}\n', "unsupported"),
    ('{"kind":"move","actor_id":"scout","direction":"west","extra":1}\n', "unexpected"),
    ('{"kind":"guard","actor_id":"scout","kind":"rest"}\n', "duplicate"),
    ('not json\n', "JSON"),
    ("x" * (MAX_INPUT_BYTES + 1), "input_too_large"),
])
def test_bad_input_rejects_without_committing_action(input_text, reason):
    result, events = _run(input_text)
    assert result["status"] == "rejected"
    assert reason.lower() in result["reason"].lower()
    assert result["session"]["state"]["tick"] == 0
    assert events[-1]["session"] == result["session"]
    assert verify_control(result["session"]) == result["session"]


def test_input_budget_checkpoint_not_false_success():
    result, _ = _run(json.dumps({
        "kind": "move", "actor_id": "scout", "direction": "east",
    }) + "\n", max_inputs=1)
    assert result["status"] == "checkpoint"
    assert result["reason"] == "input_budget_exhausted"
    assert result["session"]["state"]["phase"] == "active"


def test_source_mismatch_and_bad_team_fail_closed():
    from skeleton.game.gameplay.arena_control import new_control
    source = original_control()
    resume = new_control(source)
    altered = original_control()
    altered["score_target"] = 3
    with pytest.raises(CombatSessionError, match="source mismatch"):
        play_interactive(altered, "wayfarers", resume=resume,
                         input_stream=io.StringIO(), output_stream=io.StringIO())
    with pytest.raises(CombatSessionError, match="unknown"):
        play_interactive(source, "outsider", input_stream=io.StringIO(),
                         output_stream=io.StringIO())


def test_installed_cli_emits_replayable_checkpoint(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert main(["arena-control-interactive", "demo"]) == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert events[-1]["status"] == "checkpoint"
    assert events[-1]["reason"] == "input_eof"
    assert verify_control(events[-1]["session"]) == events[-1]["session"]
