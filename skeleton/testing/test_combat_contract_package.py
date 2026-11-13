"""Source-to-play-to-export original combat game package acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError, original_demo
from skeleton.game.gameplay.combat_contract import original_contract
from skeleton.game.gameplay.combat_contract_package import (
    build_package, cli, normalize_metadata, original_package,
    play_package, verify_package,
)


def test_original_game_package_is_playable_and_replay_verified():
    package = original_package()
    assert package["manifest"]["action_count"] == 3
    assert package["manifest"]["earned_credits"] == 14
    assert verify_package(json.loads(json.dumps(package))) == package
    saved = play_package(package)
    assert saved["state"]["phase"] == "won"
    assert saved["state"]["inventory"] == {"bridge_pass": 1}


def test_same_source_metadata_and_actions_yield_same_package():
    _, actions = original_demo()
    metadata = original_package()["manifest"]["metadata"]
    assert build_package(original_contract(), actions, metadata) == original_package()


@pytest.mark.parametrize("mutate", [
    lambda p: p["manifest"].update(earned_credits=999),
    lambda p: p["manifest"]["metadata"].update(publisher_id="someone_else"),
    lambda p: p["portable_save"]["session"]["state"].update(credits=999),
    lambda p: p["actions"][0].update(kind="guard"),
    lambda p: p["source"]["reward"].update(credits=999),
    lambda p: p.update(schema_version="forged.package.v2"),
])
def test_forged_package_rejected_even_when_checksum_is_recomputed(mutate):
    package = copy.deepcopy(original_package())
    mutate(package)
    package["checksum"] = dig({k: v for k, v in package.items()
                               if k != "checksum"})
    with pytest.raises(CombatSessionError):
        verify_package(package)


def test_unearned_objectives_cannot_be_packaged_as_victory():
    source = original_contract()
    source["objectives"].append(
        {"id": "defensive", "kind": "guard", "minimum": 1}
    )
    _, actions = original_demo()
    with pytest.raises(CombatSessionError, match="no earned"):
        build_package(source, actions, original_package()["manifest"]["metadata"])


@pytest.mark.parametrize("change", [
    lambda m: m.update(rights_declaration="public_domain_verified"),
    lambda m: m.update(title="bad\ncontrol"),
    lambda m: m.update(title=""),
    lambda m: m.update(package_id="../unsafe"),
    lambda m: m.update(extra="untrusted"),
])
def test_metadata_is_strict_but_not_a_rights_certificate(change):
    meta = original_package()["manifest"]["metadata"]
    change(meta)
    with pytest.raises(CombatSessionError):
        normalize_metadata(meta)


def test_cli_build_verify_play_is_reachable(capsys):
    from skeleton.__main__ import main
    assert main(["combat-contract-package", "demo"]) == 0
    package = json.loads(capsys.readouterr().out)
    assert cli(["verify", "--package-json", json.dumps(package)]) == 0
    assert json.loads(capsys.readouterr().out) == package
    assert cli(["play", "--package-json", json.dumps(package)]) == 0
    assert json.loads(capsys.readouterr().out)["state"]["phase"] == "won"
    assert main(["combat-contract-package", "build",
                 "--source-json", "{}", "--actions-json", "[]",
                 "--metadata-json", "{}"]) == 2
