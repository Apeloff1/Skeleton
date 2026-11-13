"""Bounded deterministic combat-contract route solver contracts."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.turn_combat import CombatSessionError
from skeleton.game.gameplay.combat_contract import (
    import_contract, original_contract, simulate_contract,
)
from skeleton.game.gameplay.combat_contract_solver import (
    cli, solve_contract, verify_solution,
)


def test_original_contract_has_replay_verified_earned_shortest_route():
    report = solve_contract(original_contract())
    assert report["session"]["state"]["phase"] == "won"
    assert report["session"]["state"]["credits"] == 14
    assert report["session"]["state"]["inventory"] == {"bridge_pass": 1}
    assert report["session"] == simulate_contract(
        original_contract(), report["actions"],
    )
    assert import_contract(report["portable_bundle"]) == report["session"]
    assert verify_solution(json.loads(json.dumps(report))) == report


def test_same_source_same_bounded_search_same_proof():
    a = solve_contract(original_contract(), max_depth=8)
    b = solve_contract(original_contract(), max_depth=8)
    assert a == b
    assert a["expanded"] <= a["max_nodes"]


def test_insufficient_depth_fails_closed():
    with pytest.raises(CombatSessionError, match="no earned contract route"):
        solve_contract(original_contract(), max_depth=1)


def test_explicit_node_budget_fails_closed():
    with pytest.raises(CombatSessionError, match="budget exhausted"):
        solve_contract(original_contract(), max_nodes=1)


def test_unearned_guard_gate_requires_guard_action():
    source = original_contract()
    source["objectives"].append(
        {"id": "defensive_discipline", "kind": "guard", "minimum": 1}
    )
    # The original speed objective allows four ticks, but a guard consumes
    # one extra player turn: keep both objectives satisfiable without
    # weakening the production solver or inventing an earned guard.
    source["objectives"][1]["maximum_turns"] = 5
    report = solve_contract(source, max_depth=10)
    assert any(a["kind"] == "guard" for a in report["actions"])
    assert report["session"]["state"]["phase"] == "won"
    assert report["session"]["state"]["objectives"]["defensive_discipline"]


def test_guard_and_original_speed_limit_are_jointly_impossible():
    source = original_contract()
    source["objectives"].append(
        {"id": "defensive_discipline", "kind": "guard", "minimum": 1}
    )
    with pytest.raises(CombatSessionError, match="no earned contract route"):
        solve_contract(source, max_depth=10)


def test_impossible_speed_gate_is_not_forged():
    source = original_contract()
    source["objectives"][1]["maximum_turns"] = 1
    with pytest.raises(CombatSessionError, match="no earned contract route"):
        solve_contract(source, max_depth=8)


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(expanded=0),
    lambda r: r["actions"][0].update(kind="guard"),
    lambda r: r["session"]["state"].update(credits=100000),
    lambda r: r.update(receipt="0" * 64),
    lambda r: r["portable_bundle"].update(checksum="0" * 64),
])
def test_tampered_solver_reports_are_rejected(mutate):
    report = copy.deepcopy(solve_contract(original_contract()))
    mutate(report)
    with pytest.raises(CombatSessionError):
        verify_solution(report)


def test_solver_cli_reachable_from_main(capsys):
    from skeleton.__main__ import main
    assert main(["combat-contract-solve", "demo"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["session"]["state"]["phase"] == "won"
    assert cli(["verify", "--report-json", json.dumps(report)]) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert main(["combat-contract-solve", "run", "--source-json", "{}"]) == 2
