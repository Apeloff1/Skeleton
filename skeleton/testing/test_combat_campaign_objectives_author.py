"""Objective authoring: CAS edit -> compile -> play -> export -> verify."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.combat_campaign_objectives import (
    normalize_objectives, original_objectives, verify_objectives_package,
)
from skeleton.game.gameplay.combat_campaign_objectives_author import (
    author_objectives, original_authoring_demo, verify_objectives_authoring,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError


def _digest(source):
    return dig(normalize_objectives(source))


def test_source_bound_authoring_compiles_real_game_and_exports():
    source = original_objectives()
    before = copy.deepcopy(source)
    receipt = author_objectives(source, [
        {"kind": "set-points", "objective_id": "guard_lantern", "value": 25},
    ], _digest(source))
    assert source == before
    assert receipt["before_digest"] != receipt["after_digest"]
    assert receipt["preview_summary"]["score"] == 35
    assert receipt["preview_package"]["manifest"]["score"] == 35
    assert verify_objectives_package(receipt["preview_package"]) == receipt["preview_package"]
    assert verify_objectives_authoring(source, json.loads(json.dumps(receipt))) == receipt


def test_add_objective_and_source_replay_are_atomic():
    source = original_objectives()
    new = {
        "objective_id": "treasury", "encounter_id": "tide_gate",
        "kind": "currency", "threshold": 30, "points": 15,
        "requires": ["clear_reeds"],
    }
    receipt = author_objectives(source, [{"kind": "add-objective", "objective": new}],
                                _digest(source))
    assert len(receipt["source"]["objectives"]) == 3
    assert receipt["preview_summary"]["score"] == 45
    assert len(source["objectives"]) == 2
    assert verify_objectives_authoring(source, receipt) == receipt


def test_remove_objective_dependency_fails_without_mutation():
    source = original_objectives()
    before = copy.deepcopy(source)
    with pytest.raises(CombatSessionError, match="dependency"):
        author_objectives(source, [
            {"kind": "remove-objective", "objective_id": "clear_reeds"},
        ], _digest(source))
    assert source == before


@pytest.mark.parametrize("operations", [
    [],
    [None],
    [{"kind": "exec", "objective_id": "clear_reeds", "value": 10}],
    [{"kind": "set-points", "objective_id": "missing", "value": 1}],
    [{"kind": "set-points", "objective_id": "clear_reeds", "value": 10}],
    [{"kind": "set-points", "objective_id": "clear_reeds", "value": True}],
    [{"kind": "set-threshold", "objective_id": "clear_reeds", "value": 1}],
    [{"kind": "set-kind", "objective_id": "clear_reeds", "value": "eval"}],
    [{"kind": "set-requires", "objective_id": "clear_reeds",
      "value": ["guard_lantern"]}],
    [{"kind": "remove-objective", "objective_id": "missing"}],
    [{"kind": "add-objective", "objective": {"bad": "source"}}],
    [{"kind": "set-points", "objective_id": "clear_reeds", "value": 1, "extra": 2}],
])
def test_invalid_operations_fail_closed(operations):
    source = original_objectives()
    with pytest.raises(CombatSessionError):
        author_objectives(source, operations, _digest(source))


def test_stale_lease_and_tampered_receipt_are_rejected():
    source = original_objectives()
    with pytest.raises(CombatSessionError, match="stale"):
        author_objectives(source, [
            {"kind": "set-points", "objective_id": "clear_reeds", "value": 11},
        ], "0" * 64)
    original = original_authoring_demo()
    for key, value in (("after_digest", "0" * 64), ("receipt", "0" * 64)):
        modified = copy.deepcopy(original)
        modified[key] = value
        with pytest.raises(CombatSessionError):
            verify_objectives_authoring(source, modified)
    modified = copy.deepcopy(original)
    modified["preview_package"]["manifest"]["score"] = 999
    with pytest.raises(CombatSessionError):
        verify_objectives_authoring(source, modified)


def test_cli_author_edit_verify_and_invalid_json(capsys):
    source = original_objectives()
    assert main(["combat-objectives-author", "edit",
                 "--source-json", json.dumps(source),
                 "--operations-json", json.dumps([{
                     "kind": "set-points", "objective_id": "guard_lantern",
                     "value": 25,
                 }]), "--expected-digest", _digest(source)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert main(["combat-objectives-author", "verify",
                 "--source-json", json.dumps(source),
                 "--receipt-json", json.dumps(receipt)]) == 0
    assert json.loads(capsys.readouterr().out) == receipt
    assert main(["combat-objectives-author", "edit",
                 "--source-json", '{"x":1,"x":2}',
                 "--operations-json", "[]",
                 "--expected-digest", "0" * 64]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
