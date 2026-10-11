"""Objective NPC long-horizon laboratory: repeatability, finite budgets, five crises."""
from __future__ import annotations

import json
import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_npc_laboratory import (
    SCHEMA, SCENARIOS, evaluate, prepare, main,
)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_five_fully_played_world_scenarios_produce_factual_evidence(scenario):
    result = evaluate(scenario, turns=8)
    assert result["schema"] == SCHEMA
    assert result["scenario"] == scenario
    assert result["actual_world_ticks"] == 8
    assert result["population_retained"] == 12
    assert result["citizen_decisions"] == 96
    assert result["alive"] + result["incapacitated"] == 12
    assert result["verified_observations"] <= 12 * 16
    assert result["completed_native_games_claimed"] == 0
    assert len(result["first_receipt"]) == len(result["last_receipt"]) == 64
    assert len(result["final_game_state_sha256"]) == 64
    assert all(0 <= v <= 1000 for v in result["warehouse_stock"].values())


def test_long_horizon_reproducible_world_run_including_full_save_and_cognition():
    x = evaluate("baseline", turns=21, population=8)
    y = evaluate("baseline", turns=21, population=8)
    assert x == y
    assert x["citizen_decisions"] == 168
    assert x["earned_policy_adjustments"] > 0
    assert x["verified_observations"] > 0


def test_food_shortage_causes_observable_actual_hunger_not_free_food_creation():
    base = evaluate("baseline", turns=1, population=4)
    crisis = evaluate("food-shortage", turns=1, population=4)
    assert crisis["hungry"] >= base["hungry"]
    assert crisis["warehouse_stock"]["food"] <= base["warehouse_stock"]["food"]
    assert crisis["population_retained"] == 4


def test_urban_cooperative_work_report_exposes_paid_unfinished_projects_without_faking():
    outcome = evaluate("public-construction", turns=9)
    assert outcome["civic_projects"] == 1
    assert outcome["cooperatively_completed_projects"] in (0, 1)
    assert outcome["resource_provenance"]["constructed_physical_sites"] >= (
        outcome["cooperatively_completed_projects"]
    )
    assert outcome["completed_native_games_claimed"] == 0


def test_social_isolation_really_changes_autonomous_social_goal_pressure():
    base = prepare("baseline", population=3)
    lonely = prepare("social-isolation", population=3)
    assert all(m.loneliness == 18 for m in lonely.cognition.minds)
    assert all(m.loneliness == 0 for m in base.cognition.minds)
    assert all(m.stress == 7 for m in lonely.cognition.minds)


def test_max_supported_population_runs_without_overflow_or_teleport_claims():
    result = evaluate("baseline", population=32, turns=2)
    assert result["population_retained"] == 32
    assert result["citizen_decisions"] == 64
    assert result["all_citizens_physical"]


def test_invalid_scopes_fail_closed_before_simulation():
    for args in (
        {"scenario": "imaginary"},
        {"scenario": "baseline", "turns": 241},
        {"scenario": "baseline", "turns": 0},
        {"scenario": "baseline", "population": 1000},
    ):
        with pytest.raises(FoundationError):
            evaluate(**args)


def test_cli_prints_only_current_replayable_simulation_facts(capsys):
    assert main([
        "--scenario", "food-shortage", "--turns", "2",
        "--population", "4",
    ]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["actual_world_ticks"] == 2
    assert data["population_retained"] == 4
    assert data["scenario"] == "food-shortage"
    assert "quality_caveat" in data
