"""Replay-verified crafting and tactical combat route search."""
import copy
import json

import pytest

from skeleton.game.gameplay.arena_forge_run import (
    original_forge, resume_forge, simulate_forge,
)
from skeleton.game.gameplay.arena_forge_solver import (
    cli, plan_forge, verify_plan,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_original_run_has_real_replayable_solution():
    source = original_forge()
    plan = plan_forge(source)
    assert plan["status"] == "found"
    assert {"kind": "craft", "recipe_id": "tide_edge"} in plan["actions"]
    assert {"kind": "equip", "recipe_id": "tide_edge"} in plan["actions"]
    result = simulate_forge(source, plan["actions"])
    assert result["state"]["phase"] == "won"
    assert result["state_digest"] == plan["final_state_digest"]
    assert verify_plan(json.loads(json.dumps(plan)), source=source) == plan


def test_resume_plan_uses_existing_verified_salvage():
    source = original_forge()
    first = simulate_forge(source, [{"kind": "fight"}])
    plan = plan_forge(session=first)
    assert plan["status"] == "found"
    assert resume_forge(first, plan["actions"])["state"]["phase"] == "won"


def test_search_depth_is_inconclusive_not_unreachable():
    assert plan_forge(original_forge(), max_depth=1)["status"] == "inconclusive"


@pytest.mark.parametrize("field,value", [
    ("status", "unreachable"), ("explored", 999),
    ("final_state_digest", "0" * 64), ("max_depth", 1),
])
def test_tampered_plan_never_certifies(field, value):
    source = original_forge()
    bad = copy.deepcopy(plan_forge(source))
    bad[field] = value
    with pytest.raises(CombatSessionError):
        verify_plan(bad, source=source)


@pytest.mark.parametrize("budget", [0, True, 513])
def test_invalid_search_budget_fails_closed(budget):
    with pytest.raises(CombatSessionError):
        plan_forge(original_forge(), max_states=budget)


def test_cli_demo_and_invalid_input(capsys):
    assert cli(["demo"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "found"
    assert cli(["plan", "--source-json", "{}"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
