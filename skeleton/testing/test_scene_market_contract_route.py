"""Budgeted market contract routing: no false impossibility and no fake wins."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market_contract import (
    original_contract, simulate_contract,
)
from skeleton.game.gameplay.scene_market_contract_route import (
    cli, solve_contract, verify_contract_route,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_budget_exhaustion_is_explicitly_inconclusive():
    source, _ = original_contract()
    report = solve_contract(source, max_nodes=1, max_depth=1)
    assert report["status"] == "inconclusive"
    assert report["actions"] is None
    assert report["terminal_state_digest"] is None
    assert verify_contract_route(source, report) == report


def test_route_witness_only_when_canonical_game_wins():
    source, _ = original_contract()
    report = solve_contract(source, max_nodes=2048, max_depth=32)
    assert report["status"] in ("found", "inconclusive")
    assert verify_contract_route(source, report) == report
    if report["status"] == "found":
        final = simulate_contract(source, report["actions"])
        assert final["state"]["phase"] == "won"
        assert final["state_digest"] == report["terminal_state_digest"]


def test_replay_witness_rejects_forged_score_even_with_checksum():
    source, actions = original_contract()
    final = simulate_contract(source, actions)
    report = {
        "schema_version": "skeleton.scene_market_contract_route.v1",
        "source_digest": final["source_digest"],
        "status": "found", "visited_nodes": 1, "actions": actions,
        "terminal_state_digest": final["state_digest"],
        "score": final["state"]["score"], "qualification": "offline_replay_witness_only",
    }
    report["checksum"] = dig(report)
    assert verify_contract_route(source, report) == report
    forged = copy.deepcopy(report)
    forged["score"] = 999
    forged["checksum"] = dig({k: v for k, v in forged.items() if k != "checksum"})
    with pytest.raises(SceneTravelError, match="replay"):
        verify_contract_route(source, forged)


def test_route_cli_reachable_and_bounded(capsys):
    from skeleton.__main__ import main
    source, _ = original_contract()
    assert main(["scene-market-contract-route", "solve",
                 "--source-json", json.dumps(source),
                 "--max-nodes", "1", "--max-depth", "1"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "inconclusive"
    assert cli(["verify", "--source-json", json.dumps(source),
                "--report-json", json.dumps(report)]) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert cli(["solve", "--source-json", json.dumps(source),
                "--max-nodes", "0"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)


@pytest.mark.parametrize("budget", [1, 2, 4, 8])
def test_frontier_budget_returns_inconclusive_without_claiming_impossibility(budget):
    source, _ = original_contract()
    report = solve_contract(source, max_nodes=budget, max_depth=32)
    assert report["visited_nodes"] <= budget
    assert report["status"] == "inconclusive"
    assert report["actions"] is None
    assert verify_contract_route(source, report) == report
