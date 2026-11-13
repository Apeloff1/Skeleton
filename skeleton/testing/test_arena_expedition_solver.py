"""Canonical expedition planner acceptance, budgets and forged-save rejection."""
from __future__ import annotations

import copy
import json
import pytest

from skeleton.game.gameplay.arena_expedition import (
    new_expedition, original_expedition, resume_expedition,
    simulate_expedition, verify_expedition,
)
from skeleton.game.gameplay.arena_expedition_solver import (
    MAX_DEPTH, MAX_STATES, cli, plan_expedition, verify_plan,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def _winning_source():
    source = original_expedition()
    # Original content remains unchanged; this variant proves an easy win.
    for stage in source["arenas"]:
        stage["arena"]["actors"][1]["max_hp"] = 1
        stage["arena"]["actors"][1]["attack"] = 1
    return source


def test_solver_witness_is_real_and_shortest():
    source = _winning_source()
    result = plan_expedition(source)
    assert result["status"] == "found"
    assert result["budget_exhausted"] is False
    assert result["actions"] == [{"kind": "fight"}, {"kind": "fight"}]
    played = simulate_expedition(source, result["actions"])
    assert played["state"]["phase"] == "won"
    assert played["state_digest"] == result["final_state_digest"]
    assert played["state"]["currency"] == result["currency"]
    assert verify_plan(json.loads(json.dumps(result)), source=source) == result


def test_original_content_has_deterministic_replayable_receipt():
    source = original_expedition()
    first = plan_expedition(source, max_states=64, max_depth=10)
    assert first == plan_expedition(source, max_states=64, max_depth=10)
    assert first["status"] in ("found", "unreachable", "inconclusive")
    if first["status"] == "found":
        saved = simulate_expedition(source, first["actions"])
        assert saved["state"]["phase"] == "won"
        assert saved["state_digest"] == first["final_state_digest"]
    else:
        assert first["actions"] == []


def test_resume_uses_actual_saved_currency_and_history():
    source = _winning_source()
    saved = simulate_expedition(source, [{"kind": "fight"}])
    resumed = plan_expedition(session=json.loads(json.dumps(saved)))
    assert resumed["status"] == "found"
    assert resumed["actions"] == [{"kind": "fight"}]
    finished = resume_expedition(saved, resumed["actions"])
    assert finished["state_digest"] == resumed["final_state_digest"]
    assert verify_plan(resumed, session=saved) == resumed


def test_terminal_save_has_no_extra_reward_actions():
    source = _winning_source()
    finished = simulate_expedition(source, [{"kind": "fight"}, {"kind": "fight"}])
    plan = plan_expedition(session=finished)
    assert plan["status"] == "found"
    assert plan["actions"] == []
    assert plan["final_state_digest"] == finished["state_digest"]
    assert verify_plan(plan, session=finished) == plan


def test_lost_save_cannot_be_resurrected_by_solver():
    source = original_expedition()
    saved = new_expedition(source)
    saved["state"]["phase"] = "lost"
    with pytest.raises(CombatSessionError):
        plan_expedition(session=saved)


@pytest.mark.parametrize("kwargs", [
    {"max_states": 0}, {"max_states": MAX_STATES + 1},
    {"max_states": True}, {"max_depth": 0},
    {"max_depth": MAX_DEPTH + 1}, {"max_depth": 1.0},
])
def test_budgets_are_strict(kwargs):
    with pytest.raises(CombatSessionError):
        plan_expedition(_winning_source(), **kwargs)


def test_tiny_depth_never_claims_unreachability():
    result = plan_expedition(_winning_source(), max_depth=1)
    assert result["status"] == "inconclusive"
    assert result["budget_exhausted"] is True
    assert result["actions"] == []


def test_tiny_state_budget_is_inconclusive():
    result = plan_expedition(_winning_source(), max_states=1)
    assert result["status"] == "inconclusive"
    assert result["budget_exhausted"] is True


@pytest.mark.parametrize("field,forged", [
    ("source_digest", "0" * 64), ("initial_state_digest", "0" * 64),
    ("status", "found"), ("final_state_digest", "0" * 64),
    ("currency", 100000), ("explored", 999),
    ("budget_exhausted", True), ("actions", [{"kind": "buy", "item_id": "tide_tonic"}]),
])
def test_forged_planner_receipt_is_rejected(field, forged):
    source = _winning_source()
    plan = plan_expedition(source)
    bad = copy.deepcopy(plan)
    bad[field] = forged
    if bad == plan:
        pytest.skip("mutation coincides with canonical receipt")
    with pytest.raises(CombatSessionError):
        verify_plan(bad, source=source)


def test_extra_receipt_field_rejected():
    source = _winning_source()
    plan = plan_expedition(source)
    plan["admin_approved"] = True
    with pytest.raises(CombatSessionError):
        verify_plan(plan, source=source)


def test_forged_resume_save_rejected():
    saved = simulate_expedition(_winning_source(), [{"kind": "fight"}])
    forged = copy.deepcopy(saved)
    forged["state"]["currency"] = 100000
    with pytest.raises(CombatSessionError):
        plan_expedition(session=forged)


def test_source_and_save_exclusive():
    with pytest.raises(CombatSessionError):
        plan_expedition()
    with pytest.raises(CombatSessionError):
        plan_expedition(_winning_source(), session=new_expedition(_winning_source()))


def test_cli_demo_and_verified_user_reachable_route(capsys):
    assert cli(["demo"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "skeleton.arena_expedition_plan.v1"
    source = _winning_source()
    assert cli(["plan", "--source-json", json.dumps(source)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert cli(["verify", "--source-json", json.dumps(source),
                "--plan-json", json.dumps(plan)]) == 0
    assert json.loads(capsys.readouterr().out) == plan
    from skeleton.__main__ import main
    assert main(["combat-expedition-solve", "plan", "--source-json",
                 json.dumps(source)]) == 0
    assert json.loads(capsys.readouterr().out) == plan


def test_cli_rejects_invalid_source(capsys):
    assert cli(["plan", "--source-json", '{"bad":true}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
