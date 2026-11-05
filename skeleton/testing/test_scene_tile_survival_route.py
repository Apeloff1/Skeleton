"""Search and replay proof for survival with actual tile collisions."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_tile_survival import (
    new_survival, original_survival, resume_survival,
)
from skeleton.game.gameplay.scene_tile_survival_route import (
    cli, legal_survival_actions, solve_survival, verify_plan,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_solver_finds_playable_source_bound_win():
    source, _ = original_survival()
    result = solve_survival(source, max_states=4096)
    assert result["status"] == "found"
    assert result["target_phase"] == "won"
    assert result["actions"]
    final = verify_plan(result, source=source)
    assert final["state"]["phase"] == "won"
    assert final["state"]["health"] > 0
    assert result["final_state_digest"] == final["state_digest"]


def test_resume_solver_from_saved_checkpoint():
    source, actions = original_survival()
    partial = resume_survival(new_survival(source), actions[:3])
    result = solve_survival(session=partial, max_states=4096)
    assert result["status"] == "found"
    assert verify_plan(result, session=partial)["state"]["phase"] == "won"


def test_actions_are_legal_and_deterministic():
    source, _ = original_survival()
    start = new_survival(source)
    actions = legal_survival_actions(start)
    assert {"kind": "tile", "action": {
        "kind": "move", "direction": "east",
    }} in actions
    assert {"kind": "rest"} not in actions
    assert legal_survival_actions(start) == actions


def test_budget_exhaustion_is_not_impossibility():
    source, _ = original_survival()
    result = solve_survival(source, max_states=1, max_depth=1)
    assert result["status"] == "inconclusive"
    assert result["budget_exhausted"] is True
    assert result["final_state_digest"] is None


def test_terminal_state_has_no_actions():
    source, actions = original_survival()
    terminal = resume_survival(new_survival(source), actions)
    assert legal_survival_actions(terminal) == []
    result = solve_survival(session=terminal)
    assert result["status"] == "found"
    assert result["actions"] == []


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(source_digest="0" * 64),
    lambda x: x.update(final_state_digest="0" * 64),
    lambda x: x.update(portable_checksum="0" * 64),
    lambda x: x["actions"][0].update(kind="rest"),
    lambda x: x.update(explored=0),
    lambda x: x.update(max_states=True),
])
def test_forged_route_witness_rejected(mutate):
    source, _ = original_survival()
    plan = solve_survival(source, max_states=4096)
    assert plan["status"] == "found"
    bad = copy.deepcopy(plan)
    mutate(bad)
    with pytest.raises(SceneTravelError):
        verify_plan(bad, source=source)


def test_invalid_target_and_missing_source():
    source, _ = original_survival()
    with pytest.raises(SceneTravelError):
        solve_survival(source, target_phase="victory")
    with pytest.raises(SceneTravelError):
        solve_survival()
    with pytest.raises(SceneTravelError):
        solve_survival(source, max_states=0)


def test_canonical_cli_demo_and_verification(capsys):
    from skeleton.__main__ import main
    assert main(["scene-survival-route", "demo"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "found"
    source, _ = original_survival()
    assert cli([
        "verify", "--source-json", json.dumps(source),
        "--plan-json", json.dumps(plan),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["phase"] == "won"
    assert cli([
        "solve", "--source-json", '{"x":1,"x":2}',
    ]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
