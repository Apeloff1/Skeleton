"""Bounded NPC shelter route search, canonical witnesses and fail-closed limits."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather_rescue import (
    new_rescue, original_rescue, play_rescue, verify_rescue,
)
from skeleton.game.gameplay.scene_weather_rescue_solver import (
    solve_rescue, verify_solution,
)


def test_original_rescue_has_replay_verified_bounded_witness():
    source, _ = original_rescue()
    receipt = solve_rescue(source)
    assert receipt["status"] == "solved"
    assert receipt["terminal"]["state"]["phase"] == "won"
    assert receipt["terminal"]["state"]["earned"] == 25
    assert play_rescue(source, receipt["actions"]) == receipt["terminal"]
    assert verify_rescue(receipt["terminal"]) == receipt["terminal"]
    assert verify_solution(json.loads(json.dumps(receipt))) == receipt


def test_budget_exhaustion_is_not_impossibility_proof():
    source, _ = original_rescue()
    result = solve_rescue(source, max_nodes=1, max_depth=0)
    assert result["status"] == "unproven_within_budget"
    assert result["terminal"] is None
    assert "not_impossibility" in result["claim"]
    assert verify_solution(result) == result


def test_solver_replays_prefix_and_rejects_stale_source():
    source, actions = original_rescue()
    prefix = play_rescue(source, actions[:2])
    receipt = solve_rescue(source, resume=prefix)
    assert receipt["start"] == prefix
    if receipt["status"] == "solved":
        assert play_rescue(source, receipt["actions"], resume=prefix) == receipt["terminal"]
    altered = copy.deepcopy(source)
    altered["npcs"][0]["reward"] = 30
    with pytest.raises(SceneTravelError, match="source mismatch"):
        solve_rescue(altered, resume=prefix)


@pytest.mark.parametrize("nodes,depth", [
    (0, 4), (257, 4), (64, -1), (64, 17), (True, 4),
])
def test_invalid_search_budgets_fail_closed(nodes, depth):
    source, _ = original_rescue()
    with pytest.raises(SceneTravelError):
        solve_rescue(source, max_nodes=nodes, max_depth=depth)


def test_tampered_witness_and_claim_rejected():
    source, _ = original_rescue()
    result = solve_rescue(source)
    bad = copy.deepcopy(result)
    bad["explored"] += 1
    with pytest.raises(SceneTravelError):
        verify_solution(bad)
    bad = copy.deepcopy(result)
    bad["terminal"]["state"]["earned"] = 10000
    with pytest.raises(SceneTravelError):
        verify_solution(bad)
    bad = copy.deepcopy(result)
    bad["actions"][0]["npc_id"] = "forged"
    with pytest.raises(SceneTravelError):
        verify_solution(bad)


def test_installed_cli_solves_and_verifies_real_rescue(capsys):
    assert main(["scene-weather-rescue-solve", "demo"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "solved"
    assert main([
        "scene-weather-rescue-solve", "verify",
        "--receipt-json", json.dumps(result),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == result
