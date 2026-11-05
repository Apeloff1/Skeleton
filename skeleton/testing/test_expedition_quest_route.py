"""Bounded quest planner must prove playable, portable, source-bound routes."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.expedition_quest import (
    demo_actions, original_quest, simulate_quest,
)
from skeleton.game.gameplay.expedition_quest_route import (
    cli, plan_quest, verify_plan,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def _near_terminal():
    return simulate_quest(original_quest(), demo_actions()[:-1])


def test_route_from_crafted_combat_checkpoint_finds_real_earned_ending():
    start = _near_terminal()
    report = plan_quest(session=start, target_ending="beacon_lit",
                        max_states=16, max_depth=2)
    assert report["status"] == "found"
    assert report["actions"] == [{"kind": "finish", "ending_id": "beacon_lit"}]
    assert report["portable_checksum"]
    assert verify_plan(json.loads(json.dumps(report)), session=start) == simulate_quest(
        original_quest(), demo_actions())


def test_alternate_ending_is_also_reachable_after_earned_victory():
    start = _near_terminal()
    report = plan_quest(session=start, target_ending="quiet_victory",
                        max_states=16, max_depth=2)
    assert report["status"] == "found"
    final = verify_plan(report, session=start)
    assert final["state"]["ending"] == "quiet_victory"
    assert final["state"]["expedition"]["state"]["phase"] == "won"


def test_small_budget_is_inconclusive_not_fabricated_unreachable():
    report = plan_quest(original_quest(), target_ending="beacon_lit",
                        max_states=1, max_depth=1)
    assert report["status"] == "inconclusive"
    assert report["budget_exhausted"] is True
    assert report["actions"] == []
    with pytest.raises(CombatSessionError, match="found"):
        verify_plan(report, source=original_quest())


def test_terminal_checkpoint_only_accepts_earned_ending():
    terminal = simulate_quest(original_quest(), demo_actions())
    found = plan_quest(session=terminal, target_ending="beacon_lit")
    assert found["status"] == "found"
    assert found["actions"] == []
    assert verify_plan(found, session=terminal) == terminal
    other = plan_quest(session=terminal, target_ending="quiet_victory")
    assert other["status"] == "unreachable"


@pytest.mark.parametrize("field,value", [
    ("source_digest", "0" * 64),
    ("final_state_digest", "0" * 64),
    ("portable_checksum", "0" * 64),
    ("explored", 999),
    ("max_states", 0),
    ("actions", []),
])
def test_forged_route_receipt_rejected(field, value):
    start = _near_terminal()
    report = plan_quest(session=start, target_ending="beacon_lit",
                        max_states=16, max_depth=2)
    bad = copy.deepcopy(report)
    bad[field] = value
    assert bad != report, "forgery fixture must modify the plan"
    with pytest.raises(CombatSessionError):
        verify_plan(bad, session=start)


@pytest.mark.parametrize("kwargs", [
    {"max_states": 0}, {"max_states": True}, {"max_states": 2049},
    {"max_depth": 0}, {"max_depth": 33},
    {"target_ending": "unknown"},
])
def test_invalid_budget_or_ending_rejected(kwargs):
    with pytest.raises(CombatSessionError):
        plan_quest(original_quest(), target_ending="beacon_lit" if
                   "target_ending" not in kwargs else kwargs["target_ending"],
                   **{k: v for k, v in kwargs.items() if k != "target_ending"})


def test_cli_reachable_and_verifies_checkpoint_witness(capsys):
    from skeleton.__main__ import main
    saved = _near_terminal()
    assert main(["quest-expedition-route", "--session-json", json.dumps(saved),
                 "--ending-id", "beacon_lit", "--max-states", "16",
                 "--max-depth", "2"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "found"
    assert cli(["--session-json", json.dumps(saved),
                "--verify-json", json.dumps(plan)]) == 0
    assert json.loads(capsys.readouterr().out)["ending"] == "beacon_lit"
