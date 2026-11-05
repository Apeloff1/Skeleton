"""Transactional fork authoring and end-to-end game delivery acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market_fork import (
    choose_market_fork, original_fork, verify_market_fork,
)
from skeleton.game.gameplay.scene_market_fork_author import (
    cli as author_cli, edit_market_fork, verify_market_fork_edit,
)
from skeleton.game.gameplay.scene_market_fork_acceptance import (
    accept_market_fork, cli as accept_cli, verify_market_fork_acceptance,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_rename_is_transactional_and_preserves_canonical_victory():
    original = original_fork()
    snapshot = copy.deepcopy(original)
    edited = edit_market_fork(original, [{
        "kind": "rename", "candidate_id": "complete_delivery",
        "new_candidate_id": "earned_victory",
    }])
    assert original == snapshot
    assert verify_market_fork_edit(edited) == edited
    assert verify_market_fork(edited["after"]) == edited["after"]
    assert edited["after"]["heuristic_candidate"] == "earned_victory"
    assert choose_market_fork(edited["after"], "earned_victory")["state"]["phase"] == "won"


def test_add_replace_remove_are_all_or_nothing():
    original = original_fork()
    edited = edit_market_fork(original, [
        {"kind": "remove", "candidate_id": "unearned_purchase"},
        {"kind": "add", "candidate": {
            "candidate_id": "wait_at_start",
            "actions": [{"kind": "tile", "action": {
                "kind": "move", "direction": "east",
            }}],
        }},
        {"kind": "replace", "candidate": {
            "candidate_id": "wait_at_start",
            "actions": [{"kind": "buy", "offer_id": "copper_badge"}],
        }},
    ])
    assert edited["after"]["outcomes"][1]["status"] == "blocked"
    assert original["outcomes"][1]["candidate_id"] == "unearned_purchase"
    with pytest.raises(SceneTravelError):
        edit_market_fork(original, [
            {"kind": "remove", "candidate_id": "complete_delivery"},
            {"kind": "remove", "candidate_id": "not_authored"},
        ])
    assert verify_market_fork(original) == original


@pytest.mark.parametrize("edits", [
    [],
    [{"kind": "remove", "candidate_id": "unknown"}],
    [{"kind": "rename", "candidate_id": "complete_delivery",
      "new_candidate_id": "unearned_purchase"}],
    [{"kind": "add", "candidate": {
        "candidate_id": "complete_delivery", "actions": [{"kind": "buy", "offer_id": "x"}],
    }}],
    [{"kind": "replace", "candidate": {
        "candidate_id": "unknown", "actions": [{"kind": "buy", "offer_id": "x"}],
    }}],
    [{"kind": "remove", "candidate_id": "complete_delivery"},
     {"kind": "remove", "candidate_id": "unearned_purchase"}],
])
def test_editor_rejects_conflicting_or_empty_publication(edits):
    with pytest.raises(SceneTravelError):
        edit_market_fork(original_fork(), edits)


def test_rejects_rewritten_author_receipt_with_recomputed_checksum():
    edited = edit_market_fork(original_fork(), [{
        "kind": "remove", "candidate_id": "unearned_purchase",
    }])
    forged = copy.deepcopy(edited)
    forged["after"]["heuristic_candidate"] = None
    forged["checksum"] = dig({k: v for k, v in forged.items() if k != "checksum"})
    with pytest.raises(SceneTravelError):
        verify_market_fork_edit(forged)


def test_acceptance_reconstructs_selected_game_ledger_and_package():
    witness = accept_market_fork(original_fork(), "complete_delivery")
    assert verify_market_fork_acceptance(witness) == witness
    assert witness["ending"] == "won"
    assert witness["ledger"]["credits_remaining"] == 1
    assert witness["ledger"]["reputation_earned"] == 5
    assert witness["selected_game_bundle"]["session"]["state"]["phase"] == "won"
    assert witness["qualification"] == "offline_gameplay_replay_only_not_device_release"


@pytest.mark.parametrize("mutate", [
    lambda w: w.update(ending="won_fake"),
    lambda w: w["ledger"].update(credits_remaining=999),
    lambda w: w["selected_game_bundle"]["session"]["state"].update(credits=999),
    lambda w: w.update(candidate_id="unearned_purchase"),
    lambda w: w.update(source_digest="0" * 64),
    lambda w: w.update(checkpoint_state_digest="0" * 64),
])
def test_acceptance_rejects_forged_gameplay_proof(mutate):
    witness = copy.deepcopy(accept_market_fork(original_fork(), "complete_delivery"))
    mutate(witness)
    witness["checksum"] = dig({k: v for k, v in witness.items() if k != "checksum"})
    with pytest.raises(SceneTravelError):
        verify_market_fork_acceptance(witness)


def test_rejects_nonwinning_or_blocked_branch():
    with pytest.raises(SceneTravelError):
        accept_market_fork(original_fork(), "unearned_purchase")


def test_cli_author_and_delivery_are_reachable(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-fork-author", "demo"]) == 0
    edited = json.loads(capsys.readouterr().out)
    assert author_cli(["verify", "--receipt-json", json.dumps(edited)]) == 0
    assert json.loads(capsys.readouterr().out) == edited
    assert main(["scene-market-fork-accept", "demo"]) == 0
    witness = json.loads(capsys.readouterr().out)
    assert accept_cli(["verify", "--witness-json", json.dumps(witness)]) == 0
    assert json.loads(capsys.readouterr().out) == witness
