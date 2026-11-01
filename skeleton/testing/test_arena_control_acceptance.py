"""Source-to-playable acceptance across author, solver, UI, save and campaign."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.arena_control import original_actions, original_control
from skeleton.game.gameplay.arena_control_acceptance import (
    accept_control, original_acceptance_demo, verify_acceptance,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_end_to_end_offline_acceptance_replays_every_component():
    result = original_acceptance_demo()
    assert result["status"] == "passed_offline_gameplay_witness"
    assert result["solver_receipt"]["status"] == "solved"
    assert result["interactive"]["status"] == "completed"
    assert result["control_package"]["manifest"]["winner"] == "wayfarers"
    assert result["campaign_package"]["manifest"]["currency"] == 1
    assert result["author_receipt"]["source"]["score_target"] == 1
    assert verify_acceptance(json.loads(json.dumps(result))) == result


def test_no_witness_is_not_mislabeled_as_release_or_success():
    result = accept_control(
        original_control(), "wayfarers",
        [{"kind": "set-score-target", "value": 1}],
        original_actions()[:1], max_nodes=1,
    )
    assert result["status"] == "unproven_within_budget"
    assert result["control_package"] is None
    assert result["campaign_package"] is None
    assert verify_acceptance(result) == result


@pytest.mark.parametrize("field", [
    "receipt", "claim", "status", "team",
])
def test_top_level_acceptance_receipt_tampering_rejected(field):
    result = original_acceptance_demo()
    bad = copy.deepcopy(result)
    bad[field] = "forged"
    with pytest.raises(CombatSessionError):
        verify_acceptance(bad)


def test_nested_export_and_interactive_evidence_tampering_rejected():
    result = original_acceptance_demo()
    bad = copy.deepcopy(result)
    bad["control_package"]["manifest"]["scores"]["wayfarers"] += 1
    with pytest.raises(CombatSessionError):
        verify_acceptance(bad)
    bad = copy.deepcopy(result)
    bad["interactive"]["events"][0]["tick"] += 1
    with pytest.raises(CombatSessionError):
        verify_acceptance(bad)
    bad = copy.deepcopy(result)
    bad["campaign_package"]["manifest"]["currency"] = 1000
    with pytest.raises(CombatSessionError):
        verify_acceptance(bad)


def test_stale_edit_and_unknown_team_fail_closed():
    with pytest.raises(CombatSessionError):
        accept_control(
            original_control(), "outsider",
            [{"kind": "set-score-target", "value": 1}],
            original_actions()[:1],
        )
    with pytest.raises(CombatSessionError):
        accept_control(
            original_control(), "wayfarers",
            [{"kind": "set-score-target", "value": 2}],
            original_actions()[:1],
        )


def test_installed_cli_runs_and_verifies_full_gameplay_vertical(capsys):
    assert main(["arena-control-accept", "demo"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "passed_offline_gameplay_witness"
    assert main([
        "arena-control-accept", "verify",
        "--receipt-json", json.dumps(result),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == result
