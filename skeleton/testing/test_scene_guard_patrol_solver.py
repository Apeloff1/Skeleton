"""Bounded patrol route search and canonical witness acceptance."""
import copy
import io
import json
from contextlib import redirect_stdout

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.scene_guard_patrol import (
    advance_patrol, original_patrol, simulate_patrol,
)
from skeleton.game.gameplay.scene_guard_patrol_solver import (
    legal_actions, solve_patrol, verify_witness,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_solver_finds_shortest_replayable_guard_route():
    source = original_patrol()
    result = solve_patrol(source)
    assert result["status"] == "witness"
    assert result["session"]["state"]["phase"] == "won"
    assert len(result["actions"]) == 3
    assert simulate_patrol(source, result["actions"]) == result["session"]
    assert verify_witness(source, result) == result


def test_solver_resumes_from_verified_checkpoint():
    source = original_patrol()
    saved = advance_patrol(
        simulate_patrol(source, []), {"kind": "collect", "pickup_id": "find_key"})
    result = solve_patrol(source, resume=saved)
    assert result["status"] == "witness"
    assert len(result["actions"]) == 2
    assert simulate_patrol(source, result["actions"], resume=saved) == result["session"]
    assert verify_witness(source, result, resume=saved) == result


def test_depth_exhaustion_is_unproven_not_false_unreachable():
    result = solve_patrol(original_patrol(), max_depth=1)
    assert result["status"] == "unproven"
    assert result["session"] is None
    assert verify_witness(original_patrol(), result) == result


def test_forged_shortest_route_and_result_fail_closed():
    source = original_patrol()
    result = solve_patrol(source)
    forged = copy.deepcopy(result)
    forged["actions"].append({"kind": "wait"})
    with pytest.raises(SceneTravelError):
        verify_witness(source, forged)
    forged = copy.deepcopy(result)
    forged["session"]["state"]["scene"]["state"]["inventory"].append("fake")
    with pytest.raises(SceneTravelError):
        verify_witness(source, forged)


def test_solver_rejects_invalid_budget_and_source_mismatch():
    source = original_patrol()
    for n in (0, 513, True):
        with pytest.raises(SceneTravelError):
            solve_patrol(source, max_nodes=n)
    for depth in (0, 33, True):
        with pytest.raises(SceneTravelError):
            solve_patrol(source, max_depth=depth)
    saved = simulate_patrol(source, [])
    changed = copy.deepcopy(source)
    changed["patrol_id"] = "different"
    with pytest.raises(SceneTravelError, match="source mismatch"):
        solve_patrol(changed, resume=saved)


def test_terminal_has_no_legal_actions():
    source = original_patrol()
    won = simulate_patrol(source, [
        {"kind": "collect", "pickup_id": "find_key"},
        {"kind": "travel", "exit_id": "north"},
        {"kind": "travel", "exit_id": "inside"},
    ])
    assert legal_actions(won) == []


def test_main_cli_demo_is_replayable():
    output = io.StringIO()
    with redirect_stdout(output):
        assert main(["scene-patrol-solve", "demo"]) == 0
    result = json.loads(output.getvalue())
    assert result["status"] == "witness"
    assert verify_witness(original_patrol(), result) == result
