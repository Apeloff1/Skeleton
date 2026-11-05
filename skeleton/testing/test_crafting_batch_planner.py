"""Multi-batch source-bound crafting, economy and CLI acceptance."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from skeleton.game.gameplay.crafting_batch_planner import (
    solve_batches, verify_batch_route,
)
from skeleton.game.gameplay.crafting_planner import CraftGoal, CraftPlanner
from skeleton.game.gameplay.crafting_runtime import (
    CraftEngine, CraftPlan, GameplayContractError,
)


def _engine() -> CraftEngine:
    path = Path(__file__).resolve().parents[2] / "docs/game/fixtures/lantern_harbor_crafting.json"
    return CraftEngine(CraftPlan.parse(json.loads(path.read_text(encoding="utf-8"))))


def test_batch_crafting_reduces_actions_without_creating_resources() -> None:
    engine = _engine()
    goal = CraftGoal("lantern", 2, "light_available")
    single = CraftPlanner(engine).solve(goal)
    result = solve_batches(engine, goal)
    assert result["status"] == "solved"
    assert len(result["actions"]) == 2
    assert len(result["actions"]) < len(single.state.actions)
    assert [a["batches"] for a in result["actions"]] == [2, 2]
    state = engine.restore(result["save"])
    assert dict(state.inventory)["lantern"] == 2
    assert state.currency == 2
    assert verify_batch_route(engine, json.loads(json.dumps(result))) == result


def test_deterministic_across_identical_source() -> None:
    engine = _engine()
    goal = CraftGoal("lantern", 2)
    assert solve_batches(engine, goal) == solve_batches(engine, goal)


def test_state_budget_conservative() -> None:
    engine = _engine()
    result = solve_batches(engine, CraftGoal("lantern", 2), max_nodes=1)
    assert result["status"] == "inconclusive"
    assert result["save"] is None
    assert verify_batch_route(engine, result) == result


def test_unreachable_when_source_has_no_recipe_for_goal() -> None:
    engine = _engine()
    result = solve_batches(engine, CraftGoal("nonexistent", 1))
    assert result["status"] == "unreachable"
    assert result["actions"] == []
    assert verify_batch_route(engine, result) == result


def test_initial_goal_already_reached() -> None:
    engine = _engine()
    result = solve_batches(engine, CraftGoal("fiber", 2))
    assert result["status"] == "solved"
    assert result["actions"] == []
    assert verify_batch_route(engine, result) == result


@pytest.mark.parametrize("field,value", [
    ("max_nodes", 0), ("max_nodes", True), ("max_nodes", 4097),
    ("max_depth", 65), ("max_depth", 0),
    ("max_batches", 0), ("max_batches", 101), ("max_batches", 1.5),
])
def test_invalid_budgets_denied(field, value) -> None:
    engine = _engine()
    with pytest.raises(GameplayContractError):
        solve_batches(engine, CraftGoal("lantern", 2), **{field: value})


@pytest.mark.parametrize("key,value", [
    ("checksum", "0" * 64),
    ("status", "unreachable"),
    ("plan_digest", "0" * 64),
    ("expanded", 0),
    ("actions", [{"sequence": 0, "recipe_id": "build_lantern", "batches": 100}]),
])
def test_forged_batch_routes_denied(key, value) -> None:
    engine = _engine()
    result = solve_batches(engine, CraftGoal("lantern", 2))
    result[key] = value
    with pytest.raises(GameplayContractError):
        verify_batch_route(engine, result)


def test_crafting_cli_batch_route_is_replayable() -> None:
    path = Path(__file__).resolve().parents[2] / "docs/game/fixtures/lantern_harbor_crafting.json"
    run = subprocess.run([
        sys.executable, "-m", "skeleton.game.gameplay.crafting_cli",
        "solve-batch", "--plan", str(path), "--goal-item", "lantern",
        "--goal-quantity", "2",
    ], capture_output=True, text=True, check=False, timeout=15)
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    assert result["status"] == "solved"
    assert len(result["actions"]) == 2
    assert verify_batch_route(_engine(), result) == result
