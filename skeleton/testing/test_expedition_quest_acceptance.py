"""Integration acceptance for NPC, crafting, combat and replayable endings."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.expedition_quest import (
    demo_actions, original_quest, simulate_quest,
)
from skeleton.game.gameplay.expedition_quest_checkpoints import (
    checkpoint_at, timeline_quest,
)
from skeleton.game.gameplay.expedition_quest_decisions import (
    apply_decision, verify_decision,
)
from skeleton.game.gameplay.expedition_quest_inventory import (
    audit_inventory, verify_audit,
)
from skeleton.game.gameplay.game_vertical_acceptance import (
    accept_vertical, cli, demo_acceptance, export_acceptance,
    import_acceptance, verify_acceptance,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_full_npc_crafting_combat_source_to_runtime_to_export():
    report = demo_acceptance("expedition_quest")
    assert report["kind"] == "expedition_quest"
    assert report["phase"] == "won"
    assert verify_acceptance(json.loads(json.dumps(report))) == report
    assert import_acceptance(export_acceptance(report)) == report
    assert report["portable_bundle"]["session"]["state"]["ending"] == "beacon_lit"


@pytest.mark.parametrize("split", [0, 1, 3, 4, 6, 8, 11])
def test_every_gameplay_checkpoint_matches_full_acceptance(split):
    report = accept_vertical(
        "expedition_quest", original_quest(), demo_actions(), checkpoint_at=split
    )
    assert report["state_digest"] == demo_acceptance("expedition_quest")["state_digest"]
    saved = simulate_quest(original_quest(), demo_actions())
    assert checkpoint_at(saved, split)["session"]["state"]["tick"] == split


def test_full_vertical_acceptance_matches_inventory_and_checkpoint_evidence():
    report = demo_acceptance("expedition_quest")
    saved = simulate_quest(original_quest(), demo_actions())
    audit = audit_inventory(saved)
    assert verify_audit(audit, saved) == audit
    assert audit["balance"] == {"signal_beacon": 1}
    assert audit["final_state_digest"] == report["state_digest"]
    timeline = timeline_quest(saved)
    assert timeline["final_state_digest"] == report["state_digest"]
    assert timeline["checkpoints"][-1]["ending"] == "beacon_lit"


def test_decision_receipt_is_real_prefix_of_accepted_game():
    start = simulate_quest(original_quest(), [])
    receipt = apply_decision(
        start, demo_actions()[0], expected_state_digest=start["state_digest"]
    )
    next_state = verify_decision(receipt)
    assert next_state == simulate_quest(original_quest(), demo_actions()[:1])
    accepted = demo_acceptance("expedition_quest")
    assert accepted["phase"] == "won"


def test_unearned_ending_and_combat_fail_acceptance():
    with pytest.raises(CombatSessionError):
        accept_vertical("expedition_quest", original_quest(), [])
    with pytest.raises(CombatSessionError):
        accept_vertical("expedition_quest", original_quest(), [
            {"kind": "finish", "ending_id": "beacon_lit"}
        ])


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(receipt="0" * 64),
    lambda x: x.update(checkpoint_digest="0" * 64),
    lambda x: x["portable_bundle"]["session"]["state"].update(items={"ore": 100}),
    lambda x: x.update(phase="won", state_digest="0" * 64),
    lambda x: x.update(checkpoint_at=True),
])
def test_forged_quest_acceptance_rejected(mutate):
    report = demo_acceptance("expedition_quest")
    bad = copy.deepcopy(report)
    mutate(bad)
    with pytest.raises(CombatSessionError):
        verify_acceptance(bad)


def test_canonical_cli_acceptance_demo_and_portable_bundle(capsys):
    from skeleton.__main__ import main
    assert main(["game-vertical-accept", "demo",
                 "--kind", "expedition_quest"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["phase"] == "won"
    assert cli(["export", "--acceptance-json", json.dumps(report)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == report
