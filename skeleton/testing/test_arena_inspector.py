"""Tactical arena timeline is replay-derived and rejects forged branches."""
from __future__ import annotations

import copy
import json
import pytest

from skeleton.game.gameplay.turn_combat import CombatSessionError
from skeleton.game.gameplay.tactical_arena import (
    _advance, cli as arena_cli, new_arena, original_arena,
)
from skeleton.game.gameplay.arena_inspector import (
    compare_sessions, inspect_session,
)


def act(kind, actor, **kwargs):
    return {"kind": kind, "actor_id": actor, **kwargs}


def test_timeline_reports_actual_movement_and_guard():
    source = original_arena()
    initial = new_arena(source)
    first = _advance(initial, act("move", "scout", direction="east"))
    second = _advance(first, act("guard", "warden"))
    report = inspect_session(second)
    assert report["turn_count"] == 2
    assert report["timeline"][0]["changed_actors"]["scout"]["before"]["position"] == [0, 1]
    assert report["timeline"][0]["changed_actors"]["scout"]["after"]["position"] == [1, 1]
    assert report["timeline"][1]["changed_actors"]["warden"]["after"]["guard"]
    assert report["state_digest"] == second["state_digest"]
    assert report == inspect_session(json.loads(json.dumps(second)))


def test_comparison_identical_prefix_divergent():
    source = original_arena()
    initial = new_arena(source)
    first = _advance(initial, act("guard", "scout"))
    second = _advance(first, act("guard", "warden"))
    alternate = _advance(first, act("rest", "warden"))
    assert compare_sessions(second, second)["relationship"] == "identical"
    prefix = compare_sessions(first, second)
    assert prefix["relationship"] == "prefix"
    assert prefix["common_turns"] == 1
    different = compare_sessions(second, alternate)
    assert different["relationship"] == "divergent"
    assert different["first_divergent_turn"] == 1


def test_different_sources_and_forged_snapshots_rejected():
    source = original_arena()
    first = _advance(new_arena(source), act("guard", "scout"))
    changed = copy.deepcopy(source)
    changed["arena_id"] = "other"
    other = new_arena(changed)
    with pytest.raises(CombatSessionError, match="different"):
        compare_sessions(first, other)
    forged = copy.deepcopy(first)
    forged["state"]["actors"]["scout"]["hp"] = 999
    with pytest.raises(CombatSessionError):
        inspect_session(forged)


def test_cli_inspect_and_compare(capsys):
    first = _advance(new_arena(original_arena()), act("guard", "scout"))
    assert arena_cli(["inspect", "--session-json", json.dumps(first)]) == 0
    assert json.loads(capsys.readouterr().out)["turn_count"] == 1
    assert arena_cli([
        "compare", "--left-json", json.dumps(first),
        "--right-json", json.dumps(first),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["relationship"] == "identical"
