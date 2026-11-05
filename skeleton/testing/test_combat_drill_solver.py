"""Replay-verified bounded offline combat training solution acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.combat_drill import (
    advance_drill, new_drill, original_drill, verify_drill,
)
from skeleton.game.gameplay.combat_drill_solver import (
    cli, solve_drill, verify_solution,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_original_training_has_real_shortest_victory_witness() -> None:
    result = solve_drill(source=original_drill())
    assert result["status"] == "solved"
    assert len(result["commands"]) == 2
    assert result["terminal_session"]["outcome"] == "passed"
    assert verify_solution(copy.deepcopy(result)) == result


def test_solution_actions_replay_through_public_drill_api() -> None:
    result = solve_drill(source=original_drill())
    cursor = new_drill(original_drill())
    for action in result["commands"]:
        cursor = advance_drill(cursor, action)
    assert cursor == result["terminal_session"]
    assert verify_drill(cursor) == cursor


def test_solver_can_resume_a_real_partial_checkpoint() -> None:
    first = advance_drill(new_drill(original_drill()), {
        "kind": "attack", "actor_id": "scout", "target_id": "warden",
    })
    result = solve_drill(session=json.loads(json.dumps(first)))
    assert result["status"] == "solved"
    assert len(result["commands"]) == 1
    assert result["terminal_session"]["outcome"] == "passed"


def test_solver_reports_depth_bound_without_claiming_unwinnable() -> None:
    result = solve_drill(source=original_drill(), max_depth=1)
    assert result["status"] == "not_found_within_depth"
    assert result["commands"] is None
    assert result["terminal_session"] is None


def test_solver_reports_state_budget_exhaustion() -> None:
    result = solve_drill(source=original_drill(), max_states=1)
    assert result["status"] == "budget_exhausted"
    assert result["explored_states"] == 1


def test_terminal_session_is_handled_without_fabricating_new_actions() -> None:
    full = solve_drill(source=original_drill())["terminal_session"]
    result = solve_drill(session=full)
    assert result["status"] == "solved"
    assert result["commands"] == []
    assert result["terminal_session"] == full


def test_invalid_limits_and_mutually_exclusive_source_rejected() -> None:
    for limit in (0, -1, 2049, True):
        with pytest.raises(CombatSessionError):
            solve_drill(source=original_drill(), max_states=limit)
    for depth in (0, 9, True):
        with pytest.raises(CombatSessionError):
            solve_drill(source=original_drill(), max_depth=depth)
    with pytest.raises(CombatSessionError):
        solve_drill()
    with pytest.raises(CombatSessionError):
        solve_drill(source=original_drill(), session=new_drill(original_drill()))


def test_forged_witness_and_status_are_rejected() -> None:
    result = solve_drill(source=original_drill())
    for field, value in [
        ("receipt", "0" * 64),
        ("status", "unsolved"),
        ("source_digest", "0" * 64),
        ("policy_version", "unknown"),
    ]:
        forged = copy.deepcopy(result)
        forged[field] = value
        with pytest.raises(CombatSessionError):
            verify_solution(forged)


def test_forged_terminal_session_rejected_even_if_checksum_recomputed() -> None:
    from skeleton.game.gameplay.flgb_gameplay_runtime import dig
    result = solve_drill(source=original_drill())
    result["terminal_session"]["combat"]["state"]["actors"]["scout"]["hp"] = 999
    result["receipt"] = dig({
        key: value for key, value in result.items() if key != "receipt"
    })
    with pytest.raises(CombatSessionError):
        verify_solution(result)


def test_canonical_cli_demo_verify_and_invalid_json(capsys) -> None:
    from skeleton.__main__ import main
    assert main(["combat-drill-solve", "demo"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "solved"
    assert cli(["verify", "--result-json", json.dumps(result)]) == 0
    assert json.loads(capsys.readouterr().out) == result
    assert cli(["verify", "--result-json", "NaN"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
