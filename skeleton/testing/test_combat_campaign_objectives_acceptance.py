"""Objective acceptance: canonical source -> gameplay -> replay -> export."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.combat_campaign_objectives import original_objectives
from skeleton.game.gameplay.combat_campaign_objectives_acceptance import (
    accept_objectives, verify_objectives_acceptance,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_full_original_campaign_is_accepted_with_replay_lineage():
    source = original_objectives()
    original = copy.deepcopy(source)
    report = accept_objectives(source)
    assert report["accepted"] is True
    assert report["issues"] == []
    assert report["completed"] == report["total"] == 2
    assert report["earned_score"] == report["maximum_score"] == 30
    assert len(report["lineage"]) == 3
    assert report["terminal_package"]["manifest"]["phase"] == "won"
    assert source == original
    assert verify_objectives_acceptance(json.loads(json.dumps(report))) == report


def test_unreachable_objective_is_not_falsely_accepted():
    source = original_objectives()
    source["objectives"][1]["kind"] = "currency"
    source["objectives"][1]["threshold"] = 1000
    report = accept_objectives(source)
    assert report["accepted"] is False
    assert report["completed"] == 1
    assert report["issues"][0]["status"] == "failed"
    assert report["issues"][0]["reason"] == "canonical_condition_failed"
    assert report["earned_score"] == 10
    assert verify_objectives_acceptance(report) == report


def test_invalid_source_does_not_produce_acceptance_evidence():
    source = original_objectives()
    source["objectives"][1]["requires"] = ["missing"]
    with pytest.raises(CombatSessionError):
        accept_objectives(source)


@pytest.mark.parametrize("edit", [
    lambda r: r.update(accepted=False),
    lambda r: r.update(completed=999),
    lambda r: r["issues"].append({"reason": "fake"}),
    lambda r: r["lineage"][1].update(earned=999),
    lambda r: r["terminal_package"]["manifest"].update(score=999),
    lambda r: r["terminal_summary"].update(score=999),
    lambda r: r.update(receipt="0" * 64),
])
def test_tampered_acceptance_evidence_fails_closed(edit):
    report = accept_objectives(original_objectives())
    tampered = copy.deepcopy(report)
    edit(tampered)
    with pytest.raises(CombatSessionError):
        verify_objectives_acceptance(tampered)


def test_cli_acceptance_and_verification(capsys):
    assert main(["combat-objectives-accept", "demo"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["accepted"] is True
    assert main(["combat-objectives-accept", "verify",
                 "--report-json", json.dumps(report)]) == 0
    assert json.loads(capsys.readouterr().out) == report


def test_cli_bad_json_fails_closed(capsys):
    assert main(["combat-objectives-accept", "audit",
                 "--source-json", '{"a":1,"a":2}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
