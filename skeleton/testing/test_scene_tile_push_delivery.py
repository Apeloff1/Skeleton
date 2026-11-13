"""Interactive push puzzle and complete portable delivery acceptance."""
from __future__ import annotations

import copy
import io
import json

import pytest

from skeleton.game.gameplay.scene_tile_push import (
    export_push, new_push, original_push, simulate_push,
)
from skeleton.game.gameplay.scene_tile_push_acceptance import accept_push
from skeleton.game.gameplay.scene_tile_push_interactive import (
    cli as play_cli, play_push,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def _input(actions):
    return io.StringIO("".join(json.dumps(action) + "\n" for action in actions))


def test_real_player_inputs_complete_and_portably_restart():
    source, actions = original_push()
    writer = io.StringIO()
    result = play_push(source, reader=_input(actions), writer=writer)
    assert result == simulate_push(source, actions)
    events = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert events[0]["event"] == "push_turn"
    assert events[0]["active_plates"] == []
    assert events[1]["event"] == "push_accepted"
    assert events[2]["event"] == "push_turn"
    assert events[2]["active_plates"] == ["gate_plate"]
    assert events[-1]["event"] == "push_terminal"
    assert events[-1]["session"] == result
    assert events[-1]["portable_checksum"] == export_push(result)["checksum"]


def test_invalid_turn_retries_without_mutating_state():
    source, actions = original_push()
    reader = io.StringIO(
        '{"kind":"move","direction":"teleport"}\n'
        + "".join(json.dumps(a) + "\n" for a in actions)
    )
    writer = io.StringIO()
    result = play_push(source, reader=reader, writer=writer)
    assert result["state"]["phase"] == "won"
    events = [json.loads(line) for line in writer.getvalue().splitlines()]
    rejected = next(x for x in events if x["event"] == "push_rejected")
    assert rejected["state_digest"] == new_push(source)["state_digest"]
    assert rejected["remaining_retries"] == 2


def test_three_invalid_turns_fail_closed_without_terminal():
    source, _ = original_push()
    writer = io.StringIO()
    reader = io.StringIO('{"kind":"teleport"}\n' * 3)
    with pytest.raises(SceneTravelError, match="three invalid"):
        play_push(source, reader=reader, writer=writer)
    events = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert [e["event"] for e in events].count("push_rejected") == 3
    assert not any(e["event"] == "push_terminal" for e in events)


def test_eof_and_truncated_line_do_not_implicitly_win():
    source, _ = original_push()
    with pytest.raises(SceneTravelError, match="ended"):
        play_push(source, reader=io.StringIO(), writer=io.StringIO())
    with pytest.raises(SceneTravelError, match="three invalid"):
        play_push(source, reader=io.StringIO("x" * 70000 + "\n" +
                  '{"kind":"teleport"}\n' * 2), writer=io.StringIO())


def test_resumed_live_checkpoint_matches_uninterrupted_play():
    source, actions = original_push()
    saved = simulate_push(source, actions[:4])
    writer = io.StringIO()
    restored = play_push(source, resume=saved,
                         reader=_input(actions[4:]), writer=writer)
    assert restored == simulate_push(source, actions)
    bad = copy.deepcopy(source)
    bad["turn_limit"] = 31
    with pytest.raises(SceneTravelError, match="mismatch"):
        play_push(bad, resume=saved, reader=io.StringIO(), writer=io.StringIO())


def test_acceptance_proves_replay_editor_and_portable_delivery():
    source, actions = original_push()
    evidence = accept_push(source, actions)
    assert evidence["phase"] == "won"
    assert evidence["verified_restart"] is True
    assert evidence["verified_editor_preview"] is True
    assert evidence["verified_export"] is True
    assert evidence["action_count"] == len(actions)
    assert evidence["final_state_digest"] == simulate_push(source, actions)["state_digest"]


def test_acceptance_refuses_partial_or_unearned_outcome():
    source, actions = original_push()
    with pytest.raises(SceneTravelError, match="earned victory"):
        accept_push(source, actions[:4])
    with pytest.raises(SceneTravelError):
        accept_push(source, [])
    with pytest.raises(SceneTravelError):
        accept_push(source, actions + [{"kind": "move", "direction": "east"}])


def test_canonical_dispatch_live_demo_and_acceptance(capsys):
    from skeleton.__main__ import main
    assert main(["scene-push-play", "demo"]) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert lines[-1]["event"] == "push_terminal"
    assert lines[-1]["phase"] == "won"
    assert main(["scene-push-accept", "demo"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["verified_restart"] is True
    assert report["phase"] == "won"
    assert play_cli(["play", "--source-json", '{"a":1,"a":2}']) == 2
    assert "error" in json.loads(capsys.readouterr().err)
