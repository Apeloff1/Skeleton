"""Authoring transactions, optimistic conflict and gameplay preview tests."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.expedition_quest import demo_actions
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.quest_factions import (
    normalize_factions, original_factions, simulate_factions,
)
from skeleton.game.gameplay.quest_factions_author import (
    apply_edits, cli, original_edit_demo, save_compatibility, verify_edits,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_demo_edit_is_playable_and_replay_verifiable():
    receipt = original_edit_demo()
    assert receipt["source"]["factions"][0]["aid_delta"] == 3
    assert receipt["preview"]["state"]["standing"]["harbor_wardens"] == 6
    assert receipt["preview"]["state"]["ending"] == "beacon_lit"
    assert verify_edits(json.loads(json.dumps(receipt))) == receipt


def test_atomic_edits_and_source_compatibility():
    source = original_factions()
    original = copy.deepcopy(source)
    receipt = apply_edits(
        source, [
            {"op": "set_members", "id": "harbor_wardens", "value": ["guide"]},
            {"op": "set_decline_delta", "id": "harbor_wardens", "value": -2},
            {"op": "set_ending_requirements", "value": []},
        ], expected_digest=dig(normalize_factions(source)),
    )
    assert source == original
    assert receipt["source_digest"] != receipt["before_digest"]
    assert verify_edits(receipt) == receipt
    saved = simulate_factions(source, demo_actions())
    assert save_compatibility(receipt, saved)["action"] == "restart_from_new_source"


def test_stale_digest_and_invalid_batch_fail_closed():
    source = original_factions()
    with pytest.raises(CombatSessionError, match="optimistic"):
        apply_edits(source, [{"op": "set_aid_delta", "id": "harbor_wardens",
                              "value": 3}], expected_digest="0" * 64)
    with pytest.raises(CombatSessionError, match="unknown faction"):
        apply_edits(source, [{"op": "set_ending_requirements", "value": [{
            "ending_id": "beacon_lit",
            "minimum_standing": [{"faction_id": "unknown", "minimum": 1}],
        }]}], expected_digest=dig(normalize_factions(source)))
    assert source == original_factions()


def test_invalid_members_and_noop_rejected():
    source = original_factions()
    with pytest.raises(CombatSessionError):
        apply_edits(source, [{"op": "set_members", "id": "harbor_wardens",
                              "value": ["unknown"]}],
                    expected_digest=dig(normalize_factions(source)))
    with pytest.raises(CombatSessionError, match="no source change"):
        apply_edits(source, [{"op": "set_aid_delta", "id": "harbor_wardens",
                              "value": 2}], expected_digest=dig(normalize_factions(source)))


def test_receipt_tampering_and_preview_mismatch_rejected():
    receipt = original_edit_demo()
    for mutate in (
        lambda x: x["preview"]["state"]["standing"].update(harbor_wardens=999),
        lambda x: x["operations"][0].update(value=4),
        lambda x: x.update(source_digest="0" * 64),
    ):
        bad = copy.deepcopy(receipt)
        mutate(bad)
        with pytest.raises(CombatSessionError):
            verify_edits(bad)


def test_cli_main_dispatch_and_receipt_roundtrip(capsys):
    from skeleton.__main__ import main
    assert main(["quest-factions-author", "demo"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["preview"]["state"]["phase"] == "finished"
    assert cli(["verify", "--receipt-json", json.dumps(receipt)]) == 0
    assert json.loads(capsys.readouterr().out) == receipt
    assert cli(["edit", "--source-json", "{}", "--operations-json", "[]",
                "--expected-digest", "bad"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
