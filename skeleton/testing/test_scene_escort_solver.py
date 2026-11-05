"""Escort route search must prove actual deliveries and fail closed on budgets."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_escort import (
    import_escort, original_escort, simulate_escort,
)
from skeleton.game.gameplay.scene_escort_solver import (
    cli, solve_escort, verify_witness,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_solver_finds_replayable_earned_supply_route():
    source = original_escort()
    report = solve_escort(source)
    assert report["status"] == "found"
    assert any(action["kind"] == "protect" for action in report["actions"])
    assert verify_witness(source, json.loads(json.dumps(report))) == report
    assert import_escort(report["bundle"]) == simulate_escort(source, report["actions"])
    assert report["bundle"]["session"]["state"]["reward"] == 20


def test_budget_exhaustion_is_not_false_unreachability():
    report = solve_escort(original_escort(), max_depth=1)
    assert report["status"] == "inconclusive"
    assert report["actions"] == []
    assert report["bundle"] is None
    report = solve_escort(original_escort(), max_states=1)
    assert report["status"] == "inconclusive"


def test_unwinnable_damage_has_no_forged_delivery():
    source = original_escort()
    source["travel_damage"] = 9
    source["max_integrity"] = 1
    report = solve_escort(source, max_depth=12)
    assert report["status"] in ("unreachable", "inconclusive")
    assert report["bundle"] is None


def test_tampered_witness_and_different_source_rejected():
    source = original_escort()
    report = solve_escort(source)
    changed = copy.deepcopy(report)
    changed["actions"][0] = {"kind": "protect"}
    with pytest.raises(SceneTravelError):
        verify_witness(source, changed)
    source["delivery_reward"] = 21
    with pytest.raises(SceneTravelError, match="source"):
        verify_witness(source, report)


def test_solver_cli_demo_and_bad_depth(capsys):
    assert cli(["demo"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "found"
    assert cli(["solve", "--source-json", json.dumps(original_escort()),
                "--max-depth", "0"]) == 2
    assert "error" in capsys.readouterr().err
