"""Bounded replayable tile routes must respect walls, pickups and exits."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_tile_route import (
    cli, legal_tile_actions, solve_tiles, verify_plan,
)
from skeleton.game.gameplay.scene_tile_walk import (
    _advance, new_tiles, original_tiles, simulate_tiles,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_solver_finds_playable_earned_key_victory():
    source, _ = original_tiles()
    plan = solve_tiles(source)
    assert plan["status"] == "found"
    assert plan["target_phase"] == "won"
    assert any(a["kind"] == "collect" for a in plan["actions"])
    assert sum(a["kind"] == "travel" for a in plan["actions"]) == 2
    assert verify_plan(json.loads(json.dumps(plan)), source=source)["state"]["phase"] == "won"
    assert simulate_tiles(source, plan["actions"])["state_digest"] == plan["final_state_digest"]


def test_solver_finds_real_failure_route():
    source, _ = original_tiles()
    plan = solve_tiles(source, target_phase="lost")
    assert plan["status"] == "found"
    assert verify_plan(plan, source=source)["state"]["phase"] == "lost"
    assert len(plan["actions"]) == 2


def test_visible_moves_never_include_wall_or_remote_pickup():
    source, _ = original_tiles()
    start = new_tiles(source)
    moves = legal_tile_actions(start)
    assert {"kind": "move", "direction": "west"} not in moves
    assert {"kind": "collect", "pickup_id": "find_key"} not in moves
    assert {"kind": "travel", "exit_id": "north"} not in moves
    assert {"kind": "move", "direction": "east"} in moves


def test_solver_from_verified_checkpoint():
    source, actions = original_tiles()
    checkpoint = simulate_tiles(source, actions[:2])
    plan = solve_tiles(session=checkpoint)
    assert plan["status"] == "found"
    assert verify_plan(plan, session=checkpoint)["state"]["phase"] == "won"


def test_exhausted_budget_is_inconclusive_not_impossible():
    source, _ = original_tiles()
    limited = solve_tiles(source, max_states=1, max_depth=1)
    assert limited["status"] == "inconclusive"
    assert limited["budget_exhausted"] is True
    with pytest.raises(SceneTravelError):
        verify_plan(limited, source=source)


@pytest.mark.parametrize("states,depth", [(0, 4), (3, 0), (2049, 4),
                                          (3, 65), (True, 4), (4, 2.0)])
def test_invalid_search_budgets_fail_closed(states, depth):
    source, _ = original_tiles()
    with pytest.raises(SceneTravelError, match="budget"):
        solve_tiles(source, max_states=states, max_depth=depth)


@pytest.mark.parametrize("tamper", [
    lambda x: x.update(final_state_digest="0" * 64),
    lambda x: x.update(portable_checksum="0" * 64),
    lambda x: x["actions"][0].update(direction="west"),
    lambda x: x.update(explored=0),
    lambda x: x.update(budget_exhausted=True),
    lambda x: x.update(extra=True),
])
def test_forged_route_receipt_rejected(tamper):
    source, _ = original_tiles()
    plan = solve_tiles(source)
    bad = copy.deepcopy(plan)
    tamper(bad)
    with pytest.raises(SceneTravelError):
        verify_plan(bad, source=source)


def test_cli_dispatch_demo_and_verify(capsys):
    from skeleton.__main__ import main
    assert main(["scene-tiles-route", "--demo"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "found"
    assert cli(["--demo", "--verify-json", json.dumps(plan)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert cli(["--demo", "--max-states", "0"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
