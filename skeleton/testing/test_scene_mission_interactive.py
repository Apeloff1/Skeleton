"""Interactive mission gameplay must be replayable, bounded and recoverable."""
from __future__ import annotations

import copy
import io
import json

import pytest

from skeleton.game.gameplay.scene_mission import (
    demo_actions, import_mission, new_mission, original_mission,
    simulate_mission, verify_mission,
)
from skeleton.game.gameplay.scene_mission_interactive import (
    cli, legal_actions, parse_player_action, play_mission,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def _events(writer):
    return [json.loads(line) for line in writer.getvalue().splitlines()]


def _input():
    return io.StringIO(
        "choose restore_lantern help\ncollect find_key\n"
        "travel north\ntravel inside\nfinish lantern_restored\n"
    )


def test_real_interactive_demo_reaches_earned_ending_and_portable_export():
    writer = io.StringIO()
    result = play_mission(original_mission(), input_stream=_input(),
                          output_stream=writer, checkpoint_every=2)
    assert result == simulate_mission(original_mission(), demo_actions())
    events = _events(writer)
    assert len([e for e in events if e["event"] == "accepted"]) == 5
    assert any(e["event"] == "checkpoint" and e["reason"] == "interval" for e in events)
    assert events[-1]["event"] == "terminal"
    assert events[-1]["ending"] == "lantern_restored"
    assert import_mission(events[-1]["bundle"]) == result


def test_eof_checkpoint_resumes_without_forging_mission_rewards():
    writer = io.StringIO()
    with pytest.raises(SceneTravelError, match="input ended"):
        play_mission(original_mission(), input_stream=io.StringIO(
            "choose restore_lantern help\n"), output_stream=writer)
    event = [e for e in _events(writer) if e["event"] == "checkpoint"][-1]
    assert event["reason"] == "input_eof"
    saved = event["session"]
    assert verify_mission(saved)["state"]["reputation"] == 3
    rest = io.StringIO("collect find_key\ntravel north\ntravel inside\nfinish lantern_restored\n")
    assert play_mission(session=saved, input_stream=rest,
                        output_stream=io.StringIO()) == simulate_mission(
                            original_mission(), demo_actions())


def test_invalid_commands_never_mutate_state_and_emit_checkpoint():
    writer = io.StringIO()
    with pytest.raises(SceneTravelError, match="retries exhausted"):
        play_mission(original_mission(), input_stream=io.StringIO(
            "finish lantern_restored\n"
            '{"kind":"choose","choice_id":"restore_lantern","option_id":"help","extra":1}\n'
            "garbage\n"
        ), output_stream=writer)
    events = _events(writer)
    assert len([e for e in events if e["event"] == "invalid"]) == 3
    saved = [e for e in events if e["event"] == "checkpoint"][-1]["session"]
    assert saved == new_mission(original_mission())


def test_turn_budget_checkpoints_accepted_prefix():
    writer = io.StringIO()
    with pytest.raises(SceneTravelError, match="budget exhausted"):
        play_mission(original_mission(), input_stream=_input(),
                     output_stream=writer, max_turns=1)
    event = [e for e in _events(writer) if e["event"] == "checkpoint"][-1]
    assert event["reason"] == "turn_budget"
    assert event["session"]["state"]["tick"] == 1


def test_source_digest_mismatch_rejected_before_output():
    writer = io.StringIO()
    with pytest.raises(SceneTravelError, match="trusted digest"):
        play_mission(original_mission(), expected_source_digest="0" * 64,
                     input_stream=_input(), output_stream=writer)
    assert writer.getvalue() == ""


def test_legal_actions_are_canonical_and_terminal_has_no_moves():
    source = original_mission()
    start = new_mission(source)
    assert {"kind": "choose", "choice_id": "restore_lantern",
            "option_id": "help"} in legal_actions(start)
    assert not any(a["kind"] == "finish" for a in legal_actions(start))
    terminal = simulate_mission(source, demo_actions())
    assert legal_actions(terminal) == []


@pytest.mark.parametrize("line", [
    "", "choose x", "travel", "collect x y", "finish",
    '{"kind":"finish","kind":"choose"}',
    '{"kind":"choose","choice_id":"x","option_id":NaN}',
    "x" * (128 * 1024 + 1),
])
def test_malformed_player_input_fails_closed(line):
    with pytest.raises(SceneTravelError):
        parse_player_action(line)


def test_terminal_resume_verifies_same_portable_game():
    terminal = simulate_mission(original_mission(), demo_actions())
    writer = io.StringIO()
    assert play_mission(session=copy.deepcopy(terminal), input_stream=io.StringIO(),
                        output_stream=writer) == terminal
    assert import_mission(_events(writer)[-1]["bundle"]) == terminal


def test_cli_reachable_from_installed_main(capsys, monkeypatch):
    from skeleton.__main__ import main
    monkeypatch.setattr("sys.stdin", _input())
    assert main(["scene-mission-play", "--demo", "--checkpoint-every", "2"]) == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert events[-1]["ending"] == "lantern_restored"


def test_cli_rejects_duplicate_key_json(capsys):
    assert cli(["--source-json", '{"a":1,"a":2}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
