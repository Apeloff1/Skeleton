"""End-to-end playable faction acceptance and tamper rejection."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.expedition_quest import demo_actions
from skeleton.game.gameplay.quest_factions import original_factions
from skeleton.game.gameplay.quest_factions_acceptance import (
    accept_vertical, cli, original_acceptance_demo, verify_acceptance,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_original_vertical_accepts_real_quest_crafting_combat_and_export():
    report = original_acceptance_demo()
    assert report["ending"] == "beacon_lit"
    assert report["standing"] == {"harbor_wardens": 4}
    assert report["crafted"] == ["beacon"]
    assert report["inventory"] == {"signal_beacon": 1}
    assert report["combat_phase"] == "won"
    assert report["earned_currency_balance"] == 25
    assert len(report["checkpoint_digests"]) == len(demo_actions()) + 1
    assert verify_acceptance(json.loads(json.dumps(report)),
                             source=original_factions()) == report


def test_no_unearned_ending_can_be_certified():
    with pytest.raises(CombatSessionError, match="requires earned finished"):
        accept_vertical(original_factions(), demo_actions()[:-1])
    with pytest.raises(CombatSessionError, match="ending mismatch"):
        accept_vertical(original_factions(), demo_actions(),
                        expected_ending="quiet_victory")


@pytest.mark.parametrize("mutation", [
    lambda x: x["standing"].update(harbor_wardens=99),
    lambda x: x.update(earned_currency_balance=999),
    lambda x: x["checkpoint_digests"].pop(),
    lambda x: x.update(portable_checksum="0" * 64),
    lambda x: x["actions"][0].update(decision="decline"),
    lambda x: x.update(checksum="0" * 64),
])
def test_acceptance_evidence_is_reconstructed_not_trusted(mutation):
    report = original_acceptance_demo()
    bad = copy.deepcopy(report)
    mutation(bad)
    with pytest.raises(CombatSessionError):
        verify_acceptance(bad, source=original_factions())


def test_source_change_invalidates_acceptance():
    report = original_acceptance_demo()
    source = original_factions()
    source["factions"][0]["aid_delta"] = 3
    with pytest.raises(CombatSessionError, match="evidence mismatch"):
        verify_acceptance(report, source=source)


def test_cli_main_dispatch_and_replay_verification(capsys):
    from skeleton.__main__ import main
    assert main(["quest-factions-accept", "demo"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ending"] == "beacon_lit"
    assert cli(["verify", "--source-json", json.dumps(original_factions()),
                "--receipt-json", json.dumps(report)]) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert cli(["accept", "--source-json", "{}", "--actions-json", "[]"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
