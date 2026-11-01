"""Search evidence is canonical, bounded and re-executable."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.combat_campaign_supply import (
    advance_supply, new_supply, original_supply, verify_supply,
)
from skeleton.game.gameplay.combat_campaign_supply_solver import (
    solve_supply, verify_supply_solution,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_survival_route_is_real_canonical_play():
    source = original_supply()
    result = solve_supply(source, min_hp=11)
    assert result["status"] == "found"
    assert result["actions"][0] == {"kind": "fight"}
    assert result["snapshot"]["state"]["phase"] == "won"
    assert result["snapshot"]["state"]["hp"] >= 11
    session = new_supply(source)
    for command in result["actions"]:
        session = advance_supply(session, command)
    assert session == result["snapshot"]
    assert verify_supply(session) == session
    assert verify_supply_solution(source, json.loads(json.dumps(result))) == result


def test_budget_exhaustion_is_not_claimed_as_unreachable():
    result = solve_supply(original_supply(), min_hp=11, max_states=1)
    assert result["status"] == "inconclusive"
    assert result["snapshot"] is None
    assert result["actions"] == []
    assert verify_supply_solution(original_supply(), result) == result


def test_depth_limit_is_explicitly_inconclusive():
    result = solve_supply(original_supply(), min_hp=11, max_depth=1)
    assert result["status"] == "inconclusive"


@pytest.mark.parametrize("options", [
    {"min_hp": True},
    {"min_hp": 0},
    {"min_hp": 13},
    {"max_states": 0},
    {"max_states": 257},
    {"max_depth": 0},
    {"max_depth": 17},
])
def test_invalid_search_budget_fails_closed(options):
    with pytest.raises(CombatSessionError):
        solve_supply(original_supply(), **options)


def test_forged_rehashed_route_and_source_fail():
    source = original_supply()
    result = solve_supply(source, min_hp=11)
    for mutation in (
        lambda r: r["actions"].pop(),
        lambda r: r.update(status="unreachable"),
        lambda r: r["snapshot"]["state"].update(hp=999),
        lambda r: r.update(expanded=0),
    ):
        forged = copy.deepcopy(result)
        mutation(forged)
        forged["receipt"] = dig({k: v for k, v in forged.items() if k != "receipt"})
        with pytest.raises(CombatSessionError):
            verify_supply_solution(source, forged)
    changed = copy.deepcopy(source)
    changed["prices"]["ward"] = 1
    with pytest.raises(CombatSessionError):
        verify_supply_solution(changed, result)


def test_cli_demo_verify_and_bad_budget(capsys):
    assert main(["combat-supply-solve", "demo", "--min-hp", "11"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "found"
    assert main(["combat-supply-solve", "verify", "--source-json",
                 json.dumps(original_supply()), "--receipt-json", json.dumps(result)]) == 0
    assert json.loads(capsys.readouterr().out) == result
    assert main(["combat-supply-solve", "demo", "--max-states", "0"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
