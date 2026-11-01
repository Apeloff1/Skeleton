"""Bounded canonical tactical capture solver and replay receipts."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.arena_control import (
    new_control, original_actions, original_control, play_control,
    resume_control, verify_control,
)
from skeleton.game.gameplay.arena_control_solver import (
    solve_control, verify_solution,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_solver_finds_replayable_player_controlled_beacon_victory():
    source = original_control()
    result = solve_control(source, "wayfarers")
    assert result["status"] == "solved"
    assert result["terminal"]["state"]["phase"] == "won"
    assert result["terminal"]["state"]["winner"] == "wayfarers"
    assert result["actions"]
    assert resume_control(result["start"], result["actions"]) == result["terminal"]
    assert verify_control(result["terminal"]) == result["terminal"]
    assert verify_solution(json.loads(json.dumps(result))) == result


def test_solver_is_deterministic_and_budget_exhaustion_is_not_impossibility():
    source = original_control()
    one = solve_control(source, "wayfarers", max_nodes=1, max_depth=0)
    assert one["status"] == "unproven_within_budget"
    assert one["terminal"] is None
    assert "not_impossibility" in one["claim"]
    assert verify_solution(one) == one
    two = solve_control(source, "wayfarers", max_nodes=64, max_depth=3)
    assert two == solve_control(copy.deepcopy(source), "wayfarers",
                               max_nodes=64, max_depth=3)


def test_solver_handles_resume_and_source_identity():
    source = original_control()
    prefix = play_control(source, original_actions()[:1])
    result = solve_control(source, "wayfarers", resume=prefix)
    assert result["start"] == prefix
    if result["status"] == "solved":
        assert result["terminal"]["state"]["winner"] == "wayfarers"
        assert resume_control(prefix, result["actions"]) == result["terminal"]
    other = copy.deepcopy(source)
    other["score_target"] = 3
    with pytest.raises(CombatSessionError, match="source mismatch"):
        solve_control(other, "wayfarers", resume=prefix)


@pytest.mark.parametrize("team,nodes,depth", [
    ("unknown", 64, 4),
    ("wayfarers", 0, 4),
    ("wayfarers", 257, 4),
    ("wayfarers", 64, -1),
    ("wayfarers", 64, 9),
    ("wayfarers", True, 3),
])
def test_solver_rejects_invalid_team_or_resource_budgets(team, nodes, depth):
    with pytest.raises(CombatSessionError):
        solve_control(original_control(), team, max_nodes=nodes, max_depth=depth)


def test_solver_receipts_reject_witness_tampering():
    result = solve_control(original_control(), "wayfarers", max_nodes=64, max_depth=3)
    altered = copy.deepcopy(result)
    altered["explored"] += 1
    with pytest.raises(CombatSessionError):
        verify_solution(altered)
    altered = copy.deepcopy(result)
    altered["start"]["state"]["scores"]["wayfarers"] = 500
    with pytest.raises(CombatSessionError):
        verify_solution(altered)
    if result["status"] == "solved":
        altered = copy.deepcopy(result)
        altered["actions"][0]["kind"] = "teleport"
        with pytest.raises(CombatSessionError):
            verify_solution(altered)


def test_solver_is_reachable_through_installed_cli(capsys):
    assert main(["arena-control-solve", "demo"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["schema_version"] == "skeleton.arena_control_solver.v1"
    assert main([
        "arena-control-solve", "verify", "--receipt-json", json.dumps(receipt),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == receipt
    assert main([
        "arena-control-solve", "solve",
        "--source-json", json.dumps(original_control()),
        "--team", "wayfarers", "--max-nodes", "1", "--max-depth", "0",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "unproven_within_budget"
