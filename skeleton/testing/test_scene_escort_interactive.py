"""Interactive convoy acceptance, recovery and bounded input handling."""
from __future__ import annotations

import io
import json

import pytest

from skeleton.game.gameplay.scene_escort import (
    demo_actions, import_escort, original_escort, resume_escort,
    simulate_escort,
)
from skeleton.game.gameplay.scene_escort_interactive import (
    legal_actions, parse_player_action, play_escort,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def _events(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_text_player_reaches_replay_verified_exported_ending():
    commands = (
        "choose restore_lantern help\n"
        "collect find_key\n"
        "protect\n"
        "travel north\n"
        "travel inside\n"
        "finish lantern_restored\n"
    )
    out = io.StringIO()
    saved = play_escort(source=original_escort(), checkpoint_every=2,
                        input_stream=io.StringIO(commands), output_stream=out)
    events = _events(out)
    assert saved == simulate_escort(original_escort(), demo_actions())
    assert events[-1]["event"] == "terminal"
    assert events[-1]["phase"] == "delivered"
    assert import_escort(events[-1]["bundle"]) == saved
    assert sum(e["event"] == "accepted" for e in events) == len(demo_actions())
    assert any(e["event"] == "checkpoint" for e in events)


def test_eof_checkpoint_resumes_from_canonical_partial_save():
    out = io.StringIO()
    with pytest.raises(SceneTravelError, match="input ended"):
        play_escort(source=original_escort(),
                    input_stream=io.StringIO("choose restore_lantern help\n"),
                    output_stream=out)
    checkpoint = [e for e in _events(out) if e["event"] == "checkpoint"][-1]
    assert checkpoint["reason"] == "input_eof"
    remaining = demo_actions()[1:]
    assert resume_escort(checkpoint["session"], remaining) == (
        simulate_escort(original_escort(), demo_actions())
    )


def test_repeated_invalid_actions_emit_checkpoint_not_rewards():
    out = io.StringIO()
    with pytest.raises(SceneTravelError, match="retries exhausted"):
        play_escort(source=original_escort(), input_stream=io.StringIO(
            "protect\nprotect\nprotect\n"
        ), output_stream=out)
    events = _events(out)
    assert [e["event"] for e in events].count("invalid") == 3
    checkpoint = [e for e in events if e["event"] == "checkpoint"][-1]
    assert checkpoint["session"]["state"]["supplies"] == 0
    assert checkpoint["session"]["state"]["reward"] == 0


def test_legal_actions_are_runtime_checked_not_guessed():
    from skeleton.game.gameplay.scene_escort import new_escort
    initial = new_escort(original_escort())
    actions = legal_actions(initial)
    assert {"kind": "protect"} not in actions
    assert {"kind": "mission", "action": {
        "kind": "choose", "choice_id": "restore_lantern", "option_id": "help",
    }} in actions


def test_source_fence_and_turn_budget_fail_closed():
    with pytest.raises(SceneTravelError, match="trusted digest"):
        play_escort(source=original_escort(), expected_source_digest="0" * 64,
                    input_stream=io.StringIO(), output_stream=io.StringIO())
    out = io.StringIO()
    with pytest.raises(SceneTravelError, match="turn budget"):
        play_escort(source=original_escort(), max_turns=1,
                    input_stream=io.StringIO("choose restore_lantern help\n"),
                    output_stream=out)
    assert any(e.get("reason") == "turn_budget" for e in _events(out))


@pytest.mark.parametrize("raw", [
    "grant 999", "protect now", "travel", "choose only",
    '{"kind":"protect","kind":"protect"}', "{" + "x" * 200000,
])
def test_invalid_player_inputs_rejected(raw):
    with pytest.raises(SceneTravelError):
        parse_player_action(raw)
