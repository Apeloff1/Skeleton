"""Actual source-bound crafting route and offline CLI acceptance."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.crafting_runtime import (
    CraftEngine, CraftPlan, CraftRecipe, GameplayContractError,
)
from skeleton.game.gameplay.crafting_planner import CraftGoal, CraftPlanner


def engine(coins: int = 10) -> CraftEngine:
    return CraftEngine(CraftPlan("lantern_harbor", [
        CraftRecipe("make_wick", (("fiber", 2),), (("wick", 1),),
                    1, (), ("wick_known",)),
        CraftRecipe("build_lantern", (("wick", 1), ("oil", 1)),
                    (("lantern", 1),), 3,
                    ("wick_known",), ("light_available",)),
    ], (("fiber", 4), ("oil", 2)), coins))


def test_shortest_canonical_crafting_route_and_portable_save() -> None:
    canonical = engine()
    route = CraftPlanner(canonical).solve(CraftGoal("lantern", 1, "light_available"))
    assert route.status == "solved"
    assert [a.recipe_id for a in route.state.actions] == [
        "make_wick", "build_lantern",
    ]
    assert route.state.currency == 6
    assert canonical.restore(route.record()["save"]) == route.state
    assert route.record()["state_digest"] == route.state.digest


def test_initial_state_goal_is_empty_replay() -> None:
    route = CraftPlanner(engine()).solve(CraftGoal("fiber", 2))
    assert route.status == "solved"
    assert route.reason == "initial-state"
    assert route.record()["actions"] == []


def test_flag_goal_is_deterministic_and_requires_one_action() -> None:
    planner = CraftPlanner(engine())
    goal = CraftGoal(required_flag="wick_known")
    first = planner.solve(goal)
    assert first.record() == planner.solve(goal).record()
    assert [a.recipe_id for a in first.state.actions] == ["make_wick"]


def test_no_funds_is_unreachable_without_minting() -> None:
    canonical = engine(0)
    route = CraftPlanner(canonical).solve(CraftGoal("lantern", 1))
    assert route.status == "unreachable"
    assert route.record()["save"] is None
    assert canonical.start().currency == 0


def test_budgets_do_not_claim_false_impossibility() -> None:
    planner = CraftPlanner(engine())
    goal = CraftGoal("lantern", 1)
    assert planner.solve(goal, max_nodes=1).reason == "node-budget-exhausted"
    assert planner.solve(goal, max_depth=1).reason == "depth-budget-exhausted"


@pytest.mark.parametrize("args", [
    {}, {"minimum_count": 1}, {"item_id": "fiber", "minimum_count": 0},
    {"item_id": "fiber", "minimum_count": True},
    {"required_flag": chr(1) + "bad"},
])
def test_invalid_goals_are_rejected(args: dict) -> None:
    with pytest.raises(GameplayContractError):
        CraftGoal(**args)


@pytest.mark.parametrize("kwargs", [
    {"max_nodes": 0}, {"max_nodes": 4097}, {"max_nodes": True},
    {"max_depth": 0}, {"max_depth": 65},
])
def test_unbounded_or_invalid_search_is_rejected(kwargs: dict) -> None:
    with pytest.raises(GameplayContractError):
        CraftPlanner(engine()).solve(CraftGoal("lantern", 1), **kwargs)


def test_real_installed_cli_solves_original_fixture(tmp_path: Path) -> None:
    fixture = (Path(__file__).resolve().parents[2] /
               "docs/game/fixtures/lantern_harbor_crafting.json")
    cmd = [
        sys.executable, "-m", "skeleton.game.gameplay.crafting_cli",
        "solve", "--plan", str(fixture), "--goal-item", "lantern",
        "--goal-flag", "light_available",
    ]
    run = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    assert result["status"] == "solved"
    assert len(result["actions"]) == 2
    canonical = CraftEngine(CraftPlan.parse(json.loads(fixture.read_text())))
    assert canonical.restore(result["save"]).digest == result["state_digest"]


def test_cli_fails_closed_on_missing_goal_or_oversized_budget() -> None:
    fixture = (Path(__file__).resolve().parents[2] /
               "docs/game/fixtures/lantern_harbor_crafting.json")
    cmd = [sys.executable, "-m", "skeleton.game.gameplay.crafting_cli",
           "solve", "--plan", str(fixture)]
    assert subprocess.run(cmd, capture_output=True, timeout=20).returncode == 2
    assert subprocess.run(
        cmd + ["--goal-item", "lantern", "--max-nodes", "100000000"],
        capture_output=True, timeout=20,
    ).returncode == 2
