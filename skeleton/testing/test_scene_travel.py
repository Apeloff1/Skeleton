"""Canonical FLGB scene travel, alternate endings and replay integrity tests."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_travel import (
    MAX_STEPS, SceneTravelError, cli, new_session, normalize_world,
    original_demo, resume_session, simulate, verify_session,
)


def test_original_story_reaches_victory_with_real_item_gate() -> None:
    world, actions = original_demo()
    result = simulate(world, actions)
    assert result["state"]["phase"] == "won"
    assert result["state"]["ending"] == "victory"
    assert result["state"]["scene_id"] == "sanctuary"
    assert result["state"]["inventory"] == ["brass_key"]
    assert result["state"]["visited"] == ["quay", "gate", "sanctuary"]
    assert result["state"]["tick"] == 3
    assert verify_session(json.loads(json.dumps(result))) == result


def test_alternate_failure_ending_is_real_and_terminal() -> None:
    world, _ = original_demo()
    result = simulate(world, [{"kind": "travel", "exit_id": "down"}])
    assert result["state"]["phase"] == "lost"
    assert result["state"]["ending"] == "failure"
    assert result["state"]["scene_id"] == "sinkhole"
    with pytest.raises(SceneTravelError, match="terminal"):
        resume_session(result, [{"kind": "travel", "exit_id": "north"}])


def test_cannot_bypass_item_requirement_or_collect_twice() -> None:
    world, actions = original_demo()
    initial = new_session(world)
    with pytest.raises(SceneTravelError, match="uncollected"):
        resume_session(initial, [actions[1]])
    with pytest.raises(SceneTravelError, match="already collected"):
        simulate(world, [actions[0], actions[0]])
    assert initial["state"]["inventory"] == []


def test_partial_save_recovery_equals_single_pass() -> None:
    world, actions = original_demo()
    partial = simulate(world, actions[:2])
    resumed = resume_session(json.loads(json.dumps(partial)), actions[2:])
    assert resumed == simulate(world, actions)
    assert resumed["save"]["parent_save_digest"] is not None


def test_authored_order_does_not_change_source_or_replay() -> None:
    world, actions = original_demo()
    reordered = copy.deepcopy(world)
    reordered["scenes"].reverse()
    for scene in reordered["scenes"]:
        scene["exits"].reverse()
        scene["pickups"].reverse()
    assert simulate(reordered, actions) == simulate(world, actions)


@pytest.mark.parametrize("change", [
    lambda w: w.update(schema_version="future"),
    lambda w: w.update(start_scene="missing"),
    lambda w: w.update(step_limit=MAX_STEPS + 1),
    lambda w: w.update(step_limit=True),
    lambda w: w["scenes"][0].update(id="../escape"),
    lambda w: w["scenes"][1].update(id="quay"),
    lambda w: w["scenes"][0]["exits"][0].update(to="missing"),
    lambda w: w["scenes"][0]["exits"][0].update(requires_item="never"),
    lambda w: w["scenes"][2].update(exits=[
        {"id": "escape", "to": "quay", "requires_item": None},
    ]),
    lambda w: w.update(extra="ignored"),
])
def test_rejects_invalid_authored_source(change) -> None:
    world, _ = original_demo()
    change(world)
    with pytest.raises(SceneTravelError):
        normalize_world(world)


@pytest.mark.parametrize("action", [
    {"kind": "travel", "exit_id": "unknown"},
    {"kind": "collect", "pickup_id": "missing"},
    {"kind": "travel", "exit_id": "north", "to": "sanctuary"},
    {"kind": "collect", "pickup_id": "../escape"},
    {"kind": "script", "code": "print('bad')"},
    {"kind": "travel", "exit_id": "north", "extra": 1},
])
def test_invalid_actions_never_mutate_existing_session(action) -> None:
    world, _ = original_demo()
    initial = new_session(world)
    original = copy.deepcopy(initial)
    with pytest.raises(SceneTravelError):
        resume_session(initial, [action])
    assert initial == original


@pytest.mark.parametrize("tamper", [
    lambda s: s["state"].update(scene_id="sanctuary"),
    lambda s: s["state"]["inventory"].append("master_key"),
    lambda s: s["journal"][0].update(receipt="0" * 64),
    lambda s: s["journal"].reverse(),
    lambda s: s["save"].update(parent_save_digest=None),
    lambda s: s.update(source_digest="0" * 64),
    lambda s: s.update(event_bus_digest="0" * 64),
])
def test_replay_rejects_modified_state_and_history(tamper) -> None:
    world, actions = original_demo()
    session = simulate(world, actions)
    tamper(session)
    with pytest.raises(SceneTravelError):
        verify_session(session)


def test_step_budget_draws_without_unbounded_loop() -> None:
    world, _ = original_demo()
    world["step_limit"] = 1
    session = simulate(world, [{"kind": "collect", "pickup_id": "find_key"}])
    assert session["state"]["phase"] == "draw"
    with pytest.raises(SceneTravelError):
        resume_session(session, [{"kind": "travel", "exit_id": "north"}])


def test_cli_demo_verify_and_resume_roundtrip(capsys) -> None:
    assert cli(["demo"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["state"]["phase"] == "won"
    assert cli(["verify", "--session-json", json.dumps(result)]) == 0
    assert json.loads(capsys.readouterr().out) == result
    world, actions = original_demo()
    partial = simulate(world, actions[:2])
    assert cli([
        "resume", "--session-json", json.dumps(partial),
        "--actions-json", json.dumps(actions[2:]),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == result


def test_cli_rejects_invalid_json_and_untrusted_actions(capsys) -> None:
    assert cli([
        "simulate", "--world-json", "{", "--actions-json", "[]",
    ]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
    world, _ = original_demo()
    assert cli([
        "simulate", "--world-json", json.dumps(world),
        "--actions-json", json.dumps([{"kind": "script"}]),
    ]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
