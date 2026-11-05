"""Mission ending solver must use actual canonical scene and quest transitions."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_mission import (
    demo_actions, original_mission, resume_mission, simulate_mission,
)
from skeleton.game.gameplay.scene_mission_solver import (
    cli, plan_ending, verify_plan,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_finds_real_restored_ending_with_replayable_actions():
    source = original_mission()
    plan = plan_ending(source, target_ending="lantern_restored")
    assert plan["status"] == "found"
    assert plan["budget_exhausted"] is False
    assert plan["target_ending"] == "lantern_restored"
    result = verify_plan(plan, source=source)
    assert result["state"]["ending"] == "lantern_restored"
    assert result["state"]["missions"] == [
        "pledge", "recover_key", "reach_sanctuary",
    ]
    assert plan["final_state_digest"] == result["state_digest"]
    assert len(plan["actions"]) <= len(demo_actions())


def test_resume_from_midgame_returns_only_remaining_actions():
    source = original_mission()
    first = simulate_mission(source, demo_actions()[:2])
    plan = plan_ending(session=first, target_ending="lantern_restored")
    assert plan["status"] == "found"
    assert verify_plan(plan, session=first)["state"]["ending"] == "lantern_restored"
    assert len(plan["actions"]) < len(demo_actions())


def test_failure_and_alternate_victory_are_reachable():
    source = original_mission()
    for ending in ("sinkhole_failure", "unpledged_victory"):
        plan = plan_ending(source, target_ending=ending)
        assert plan["status"] == "found"
        assert verify_plan(plan, source=source)["state"]["ending"] == ending


def test_terminal_saved_session_is_not_misrepresented():
    source = original_mission()
    terminal = simulate_mission(source, demo_actions())
    matched = plan_ending(session=terminal, target_ending="lantern_restored")
    assert matched["status"] == "found"
    assert matched["actions"] == []
    assert verify_plan(matched, session=terminal) == terminal
    mismatch = plan_ending(session=terminal, target_ending="sinkhole_failure")
    assert mismatch["status"] == "unreachable"


def test_budget_exhaustion_is_inconclusive_not_unreachable():
    plan = plan_ending(original_mission(), target_ending="lantern_restored",
                       max_states=1, max_depth=1)
    assert plan["status"] == "inconclusive"
    assert plan["budget_exhausted"] is True
    assert plan["actions"] == []


@pytest.mark.parametrize("kwargs", [
    {"max_states": 0},
    {"max_states": True},
    {"max_states": 4097},
    {"max_depth": 0},
    {"max_depth": 129},
])
def test_bad_search_budgets_rejected(kwargs):
    with pytest.raises(SceneTravelError):
        plan_ending(original_mission(), target_ending="lantern_restored", **kwargs)


def test_source_tamper_and_forged_witness_are_rejected():
    source = original_mission()
    plan = plan_ending(source, target_ending="lantern_restored")
    forged = copy.deepcopy(plan)
    forged["final_state_digest"] = "0" * 64
    with pytest.raises(SceneTravelError, match="witness"):
        verify_plan(forged, source=source)
    forged = copy.deepcopy(plan)
    forged["actions"] = []
    with pytest.raises(SceneTravelError, match="witness"):
        verify_plan(forged, source=source)
    modified = copy.deepcopy(source)
    modified["choices"][0]["options"][0]["reputation"] = 3
    with pytest.raises(SceneTravelError, match="source"):
        verify_plan(plan, source=modified)


def test_missing_target_and_unsupported_receipt_fail_closed():
    with pytest.raises(SceneTravelError, match="unknown"):
        plan_ending(original_mission(), target_ending="missing")
    with pytest.raises(SceneTravelError):
        verify_plan({"schema_version": "future"}, source=original_mission())


def test_installed_cli_emits_valid_route(capsys):
    from skeleton.__main__ import main
    assert main(["scene-mission-route", "--demo"]) == 0
    route = json.loads(capsys.readouterr().out)
    assert route["status"] == "found"
    assert verify_plan(route, source=original_mission())["state"]["phase"] == "finished"
    assert cli(["--demo", "--ending-id", "missing"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
