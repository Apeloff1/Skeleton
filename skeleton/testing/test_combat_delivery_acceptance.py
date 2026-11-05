"""Combat package and replay acceptance cannot diverge."""
import copy
import json

import pytest

from skeleton.game.gameplay.combat_delivery_acceptance import (
    build_delivery, cli, original_delivery, play_delivery,
    verify_delivery,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, original_demo,
)
from skeleton.game.gameplay.combat_contract import original_contract
from skeleton.game.gameplay.combat_contract_package import original_package


def test_original_delivery_replays_package_and_acceptance():
    delivery = original_delivery()
    assert verify_delivery(delivery) == delivery
    assert delivery["acceptance"]["phase"] == "won"
    assert delivery["acceptance"]["portable_bundle"] == (
        delivery["package"]["portable_save"]
    )
    played = play_delivery(delivery)
    assert played["ok"] is True
    assert played["phase"] == "won"
    assert played["credits"] == 14
    assert played["inventory"] == {"bridge_pass": 1}


def test_delivery_acceptance_matches_canonical_original_game():
    package = original_package()
    _, actions = original_demo()
    built = build_delivery(
        original_contract(), actions, package["manifest"]["metadata"])
    assert built == original_delivery()
    assert built["source_digest"] == package["manifest"]["source_digest"]
    assert built["state_digest"] == package["manifest"]["state_digest"]


def test_tampering_cross_system_lineage_and_rights_fails_closed():
    original = original_delivery()
    for field, value in (
        ("source_digest", "0" * 64),
        ("state_digest", "0" * 64),
        ("manifest_digest", "0" * 64),
        ("receipt", "0" * 64),
    ):
        altered = copy.deepcopy(original)
        altered[field] = value
        with pytest.raises(CombatSessionError):
            verify_delivery(altered)
    altered = copy.deepcopy(original)
    altered["package"]["manifest"]["metadata"]["rights_declaration"] = (
        "unknown_unlicensed"
    )
    with pytest.raises(CombatSessionError):
        verify_delivery(altered)
    altered = copy.deepcopy(original)
    altered["acceptance"]["portable_bundle"]["session"]["state"]["credits"] += 1
    with pytest.raises(CombatSessionError):
        verify_delivery(altered)


def test_delivery_cli_build_verify_and_play(capsys):
    assert cli(["demo"]) == 0
    delivered = json.loads(capsys.readouterr().out)
    assert cli(["verify", "--delivery-json", json.dumps(delivered)]) == 0
    assert json.loads(capsys.readouterr().out) == delivered
    assert cli(["play", "--delivery-json", json.dumps(delivered)]) == 0
    played = json.loads(capsys.readouterr().out)
    assert played["phase"] == "won"
    package = original_package()
    assert cli([
        "build", "--source-json", json.dumps(original_contract()),
        "--actions-json", json.dumps(package["actions"]),
        "--metadata-json", json.dumps(package["manifest"]["metadata"]),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == delivered
