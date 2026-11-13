"""Bounded victory solver proves routes through the real scene transition engine."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_route_solver import cli, plan_victory
from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, original_demo, simulate, verify_session,
)


def test_original_victory_route_is_replayed_not_fabricated() -> None:
    world, expected = original_demo()
    result = plan_victory(world)
    assert result["status"] == "found"
    assert result["budget_exhausted"] is False
    assert result["actions"] == expected
    replay = simulate(world, result["actions"])
    assert replay["state"]["phase"] == "won"
    assert replay["state_digest"] == result["final_state_digest"]
    assert replay["source_digest"] == result["source_digest"]


def test_route_from_verified_partial_save_only_returns_remaining_actions() -> None:
    world, actions = original_demo()
    partial = simulate(world, actions[:1])
    result = plan_victory(session=json.loads(json.dumps(partial)))
    assert result["status"] == "found"
    assert result["actions"] == actions[1:]
    replay = verify_session(partial)
    from skeleton.game.gameplay.scene_travel import resume_session
    final = resume_session(replay, result["actions"])
    assert final["state_digest"] == result["final_state_digest"]


def test_terminal_victory_and_failure_are_distinct() -> None:
    world, actions = original_demo()
    won = simulate(world, actions)
    lost = simulate(world, [{"kind": "travel", "exit_id": "down"}])
    assert plan_victory(session=won)["status"] == "found"
    assert plan_victory(session=won)["actions"] == []
    result = plan_victory(session=lost)
    assert result["status"] == "unreachable"
    assert result["budget_exhausted"] is False


def test_exhaustive_no_victory_path_is_unreachable() -> None:
    world, _ = original_demo()
    world["scenes"][0]["exits"] = [
        edge for edge in world["scenes"][0]["exits"]
        if edge["id"] != "north"
    ]
    result = plan_victory(world)
    assert result["status"] == "unreachable"
    assert result["budget_exhausted"] is False
    assert result["actions"] == []


def test_search_budget_truncation_is_not_misreported_as_impossible() -> None:
    world, _ = original_demo()
    shallow = plan_victory(world, max_depth=1)
    assert shallow["status"] == "inconclusive"
    assert shallow["budget_exhausted"] is True
    bounded = plan_victory(world, max_states=1)
    assert bounded["status"] == "inconclusive"
    assert bounded["budget_exhausted"] is True


def test_authored_scene_order_has_no_effect_on_proof() -> None:
    world, _ = original_demo()
    reversed_world = copy.deepcopy(world)
    reversed_world["scenes"].reverse()
    assert plan_victory(world) == plan_victory(reversed_world)


@pytest.mark.parametrize("kwargs", [
    {"max_states": 0}, {"max_states": 4097},
    {"max_states": True}, {"max_depth": 0},
    {"max_depth": 513}, {"max_depth": False},
])
def test_invalid_resource_budgets_fail_closed(kwargs) -> None:
    world, _ = original_demo()
    with pytest.raises(SceneTravelError):
        plan_victory(world, **kwargs)


def test_tampered_save_never_enters_search() -> None:
    world, actions = original_demo()
    partial = simulate(world, actions[:1])
    partial["state"]["inventory"].append("master_key")
    with pytest.raises(SceneTravelError):
        plan_victory(session=partial)


def test_cli_returns_replayable_route_and_invalid_json_error(capsys) -> None:
    assert cli(["--demo"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "found"
    world, _ = original_demo()
    assert simulate(world, result["actions"])["state"]["phase"] == "won"
    assert cli(["--world-json", "{"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False


def test_installed_cli_scene_hint_uses_same_solver(capsys) -> None:
    from skeleton.__main__ import main
    assert main(["scene-travel", "hint", "--demo"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "found"
    assert len(result["actions"]) == 3
