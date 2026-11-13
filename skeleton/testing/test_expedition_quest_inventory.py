"""Real earned NPC gifts and crafting inventory must conserve every unit."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.expedition_quest import (
    demo_actions, new_quest, original_quest, simulate_quest,
)
from skeleton.game.gameplay.expedition_quest_inventory import (
    audit_inventory, cli, item_proof, verify_audit,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


@pytest.fixture
def saved():
    return simulate_quest(original_quest(), demo_actions())


def test_original_quest_proves_all_gifts_and_consumed_ingredients(saved):
    audit = audit_inventory(saved)
    assert audit["balance"] == {"signal_beacon": 1}
    assert audit["credits"] == {"ore": 1, "reed": 1, "signal_beacon": 1}
    assert audit["debits"] == {"ore": 1, "reed": 1}
    assert len(audit["entries"]) == 3
    assert audit["ending"] == "beacon_lit"
    assert audit == verify_audit(json.loads(json.dumps(audit)), saved)


def test_ingredient_provenance_explains_crafting_consumption(saved):
    reed = item_proof(saved, "reed")
    assert reed["credits"] == 1
    assert reed["debits"] == 1
    assert reed["balance"] == 0
    assert [entry["delta"] for entry in reed["history"]] == [1, -1]
    beacon = item_proof(saved, "signal_beacon")
    assert beacon["credits"] == 1
    assert beacon["debits"] == 0
    assert beacon["balance"] == 1
    assert beacon["history"][0]["action"]["kind"] == "craft"


def test_declined_npc_does_not_award_gift():
    start = original_quest()
    played = simulate_quest(start, [
        {"kind": "talk", "npc_id": "guide", "decision": "decline"}
    ])
    audit = audit_inventory(played)
    assert audit["entries"] == []
    assert audit["balance"] == {}
    assert audit["choices"] == {"guide": "decline"}


def test_no_actions_produce_zero_inventory_provenance():
    saved = new_quest(original_quest())
    report = audit_inventory(saved)
    assert report["tick"] == 0
    assert report["entries"] == []
    assert report["credits"] == {}
    assert report["debits"] == {}


@pytest.mark.parametrize("tamper", [
    lambda x: x.update(checksum="0" * 64),
    lambda x: x["credits"].update(ore=2),
    lambda x: x["balance"].update(signal_beacon=99),
    lambda x: x["entries"][0]["changes"].update(reed=999),
    lambda x: x["entries"][1].update(action_receipt="0" * 64),
    lambda x: x.update(portable_checksum="0" * 64),
    lambda x: x.update(extra=True),
])
def test_audit_mutation_fails_replay(saved, tamper):
    original = audit_inventory(saved)
    changed = copy.deepcopy(original)
    tamper(changed)
    with pytest.raises(CombatSessionError):
        verify_audit(changed, saved)


def test_forged_save_inventory_fails_before_audit(saved):
    forged = copy.deepcopy(saved)
    forged["state"]["items"]["ore"] = 500
    with pytest.raises(CombatSessionError):
        audit_inventory(forged)


def test_cli_dispatch_and_proof(capsys, saved):
    from skeleton.__main__ import main
    assert main(["quest-inventory", "demo"]) == 0
    audit = json.loads(capsys.readouterr().out)
    assert audit["balance"] == {"signal_beacon": 1}
    assert cli(["verify", "--session-json", json.dumps(saved),
                "--audit-json", json.dumps(audit)]) == 0
    assert json.loads(capsys.readouterr().out) == audit
    assert cli(["prove", "--session-json", json.dumps(saved),
                "--item-id", "reed"]) == 0
    assert json.loads(capsys.readouterr().out)["balance"] == 0
    assert cli(["prove", "--session-json", json.dumps(saved),
                "--item-id", "bad item"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)


def test_unknown_item_proof_is_explicit_zero_not_fake_reward(saved):
    proof = item_proof(saved, "unknown_item")
    assert proof["history"] == []
    assert proof["credits"] == proof["debits"] == proof["balance"] == 0
