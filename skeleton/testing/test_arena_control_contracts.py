"""Playable capture contracts: source, action, replay, editing, portable save and CLI."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.arena_control import original_actions
from skeleton.game.gameplay.arena_control_contracts import (
    normalize_contract, original_contract, new_contract, play_contract,
    resume_contract, verify_contract, package_contract, verify_package,
)
from skeleton.game.gameplay.arena_control_contracts_author import (
    author_contract, verify_author_receipt,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_original_bounty_earned_only_by_real_terminal_win():
    session = play_contract(original_contract(), original_actions())
    assert session["state"]["phase"] == "won"
    assert session["state"]["reward"] == 50
    assert all(item["achieved"] for item in session["state"]["objectives"])
    assert verify_contract(json.loads(json.dumps(session))) == session
    package = package_contract(session)
    assert verify_package(json.loads(json.dumps(package))) == package
    assert package["manifest"]["reward"] == 50


def test_resume_after_each_turn_is_byte_identical_to_single_play():
    source = original_contract()
    first = new_contract(source)
    assert first["state"]["reward"] == 0
    for action in original_actions():
        first = resume_contract(first, [action])
    assert first == play_contract(source, original_actions())


def test_unfinished_capture_does_not_mint_rewards():
    session = play_contract(original_contract(), original_actions()[:1])
    assert session["state"]["phase"] == "active"
    assert session["state"]["reward"] == 0
    assert verify_contract(session) == session


@pytest.mark.parametrize("mutate", [
    lambda x: x["state"].update(reward=9999),
    lambda x: x["control_session"]["state"]["scores"].update(wayfarers=999),
    lambda x: x["save"].update(parent_save_digest="forged"),
    lambda x: x["source"]["objectives"][0].update(reward=100000),
    lambda x: x["control_session"]["journal"][0].update(receipt="forged"),
])
def test_forged_nested_source_score_rewards_and_lineage_rejected(mutate):
    bad = copy.deepcopy(play_contract(original_contract(), original_actions()))
    mutate(bad)
    with pytest.raises(CombatSessionError):
        verify_contract(bad)


def test_contract_source_validation_and_boundaries():
    source = original_contract()
    source["objectives"].append(copy.deepcopy(source["objectives"][0]))
    with pytest.raises(CombatSessionError, match="duplicate"):
        normalize_contract(source)
    source = original_contract()
    source["objectives"][0]["target"] = "nonexistent_zone"
    with pytest.raises(CombatSessionError, match="unknown"):
        normalize_contract(source)
    source = original_contract()
    source["objectives"][0]["reward"] = 100001
    with pytest.raises(CombatSessionError):
        normalize_contract(source)
    source = original_contract()
    source["player_team"] = "impostor"
    with pytest.raises(CombatSessionError):
        normalize_contract(source)


def test_no_extra_action_after_terminal_and_invalid_action_fails_closed():
    terminal = play_contract(original_contract(), original_actions())
    with pytest.raises(CombatSessionError):
        resume_contract(terminal, original_actions()[:1])
    checkpoint = new_contract(original_contract())
    with pytest.raises(CombatSessionError):
        resume_contract(checkpoint, [{"kind": "move", "actor_id": "impostor", "direction": "east"}])
    assert verify_contract(checkpoint) == checkpoint


def test_atomic_edit_with_playable_preview_and_stale_digest_rejection():
    source = original_contract()
    operation = [{"kind": "set-reward", "objective_id": "secure_west", "value": 17}]
    receipt = author_contract(source, operation, dig(normalize_contract(source)), original_actions())
    assert receipt["preview"]["state"]["reward"] == 52
    assert verify_author_receipt(json.loads(json.dumps(receipt))) == receipt
    with pytest.raises(CombatSessionError, match="stale"):
        author_contract(source, operation, "old", original_actions())
    with pytest.raises(CombatSessionError, match="no-op"):
        author_contract(source, [{"kind": "set-reward", "objective_id": "secure_west", "value": 15}],
                        dig(normalize_contract(source)), original_actions())


def test_author_preview_and_package_tamper_rejected():
    source = original_contract()
    receipt = author_contract(source, [
        {"kind": "set-target", "objective_id": "fast_finish", "value": 2},
    ], dig(normalize_contract(source)), original_actions())
    bad = copy.deepcopy(receipt)
    bad["preview"]["state"]["reward"] = 999
    with pytest.raises(CombatSessionError):
        verify_author_receipt(bad)
    package = package_contract(play_contract(source, original_actions()))
    bad = copy.deepcopy(package)
    bad["manifest"]["reward"] = 999
    with pytest.raises(CombatSessionError):
        verify_package(bad)


def test_installed_cli_demo_verify_export_and_author(capsys):
    assert main(["arena-control-contracts", "demo"]) == 0
    session = json.loads(capsys.readouterr().out)
    assert session["state"]["reward"] == 50
    assert main(["arena-control-contracts", "verify",
                 "--session-json", json.dumps(session)]) == 0
    assert json.loads(capsys.readouterr().out) == session
    assert main(["arena-control-contracts", "pack",
                 "--session-json", json.dumps(session)]) == 0
    package = json.loads(capsys.readouterr().out)
    assert main(["arena-control-contracts", "unpack",
                 "--package-json", json.dumps(package)]) == 0
    assert json.loads(capsys.readouterr().out) == package
    assert main(["arena-control-contracts-author", "demo"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["preview"]["state"]["reward"] == 52
    assert main(["arena-control-contracts-author", "verify",
                 "--receipt-json", json.dumps(receipt)]) == 0
    assert json.loads(capsys.readouterr().out) == receipt
