"""Circuit shortest-route acceptance and fail-closed bounded search."""
import copy
import json

import pytest

from skeleton.game.gameplay.scene_circuit import (
    original_circuit, simulate_circuit, resume_circuit,
)
from skeleton.game.gameplay.scene_circuit_solver import (
    cli, plan_circuit, verify_plan,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_shortest_route_uses_real_switch_and_pickup():
    source, _ = original_circuit()
    result = plan_circuit(source)
    assert result["status"] == "found"
    assert len(result["actions"]) == 4
    assert {"kind": "toggle", "switch_id": "quay_lantern"} in result["actions"]
    assert {"kind": "collect", "pickup_id": "find_key"} in result["actions"]
    played = simulate_circuit(source, result["actions"])
    assert played["state"]["scene"]["state"]["phase"] == "won"
    assert played["state_digest"] == result["final_state_digest"]
    assert verify_plan(json.loads(json.dumps(result)), source=source) == result


def test_plan_from_verified_checkpoint_is_replayable():
    source, actions = original_circuit()
    first = simulate_circuit(source, actions[:2])
    result = plan_circuit(session=json.loads(json.dumps(first)))
    assert result["status"] == "found"
    resumed = resume_circuit(first, result["actions"])
    assert resumed["state"]["scene"]["state"]["phase"] == "won"


def test_depth_and_state_budgets_are_inconclusive():
    source, _ = original_circuit()
    assert plan_circuit(source, max_depth=1)["status"] == "inconclusive"
    assert plan_circuit(source, max_states=1)["budget_exhausted"] is True


def test_terminal_victory_has_empty_plan():
    source, actions = original_circuit()
    won = simulate_circuit(source, actions)
    result = plan_circuit(session=won)
    assert result["status"] == "found"
    assert result["actions"] == []
    assert result["initial_state_digest"] == result["final_state_digest"]


def test_mutated_plan_is_not_certified():
    source, _ = original_circuit()
    plan = plan_circuit(source)
    for field, value in [
        ("status", "unreachable"),
        ("final_state_digest", "0" * 64),
        ("explored", 999),
        ("max_depth", 1),
    ]:
        bad = copy.deepcopy(plan)
        bad[field] = value
        with pytest.raises(SceneTravelError):
            verify_plan(bad, source=source)


@pytest.mark.parametrize("budget", [0, True, 4097])
def test_invalid_state_budget_rejected(budget):
    source, _ = original_circuit()
    with pytest.raises(SceneTravelError):
        plan_circuit(source, max_states=budget)


def test_cli_demo_and_invalid_plan(capsys):
    assert cli(["demo"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "found"
    assert cli(["verify", "--source-json", "{}", "--plan-json", "{}"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
