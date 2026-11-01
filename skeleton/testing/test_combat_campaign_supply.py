"""Earned supplies integrate canonical combat, save lineage, authoring and CLI."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.combat_campaign_supply import (
    SCHEMA, advance_supply, available_supply, finish_supply, new_supply,
    normalize_supply, original_supply, package_supply, verify_supply,
    verify_supply_package,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_original_source_to_fight_to_save_to_export():
    source = original_supply()
    before = copy.deepcopy(source)
    initial = new_supply(source)
    assert available_supply(initial)["actions"] == [{"kind": "fight"}]
    first = advance_supply(initial, {"kind": "fight"})
    assert first["state"]["currency"] == 10
    assert first["state"]["hp"] < 12
    assert first["save"]["parent_digest"] is not None
    assert first["state"]["battles"][0]["combat"]["state"]["phase"] == "won"
    final = finish_supply(source, resume=first)
    assert final["state"]["phase"] == "won"
    assert final == finish_supply(source)
    assert verify_supply(json.loads(json.dumps(final))) == final
    assert verify_supply_package(json.loads(json.dumps(package_supply(final))))
    assert source == before


def test_earned_medkit_and_ward_change_canonical_outcomes():
    source = original_supply()
    first = advance_supply(new_supply(source), {"kind": "fight"})
    bought = advance_supply(first, {"kind": "buy", "item": "medkit"})
    healed = advance_supply(bought, {"kind": "use", "item": "medkit"})
    assert healed["state"]["hp"] == 12
    assert healed["state"]["currency"] == 2
    assert healed["state"]["inventory"]["medkit"] == 0
    finished = advance_supply(healed, {"kind": "fight"})
    assert finished["state"]["phase"] == "won"
    assert verify_supply(finished) == finished
    ward = advance_supply(first, {"kind": "buy", "item": "ward"})
    ward = advance_supply(ward, {"kind": "use", "item": "ward"})
    assert ward["state"]["ward_active"] is True
    assert ward["state"]["currency"] == 0
    defended = advance_supply(ward, {"kind": "fight"})
    assert defended["state"]["battles"][1]["ward_used"] is True
    assert defended["state"]["phase"] == "won"
    assert defended["state"]["hp"] >= finished["state"]["hp"] - 4
    assert verify_supply(defended) == defended


@pytest.mark.parametrize("command", [
    {"kind": "buy", "item": "medkit"},
    {"kind": "use", "item": "medkit"},
    {"kind": "use", "item": "ward"},
    {"kind": "fight", "extra": True},
    {"kind": "unknown"},
    {"kind": "buy", "item": "sword"},
    {"kind": "fight", "item": "ward"},
    {"kind": True},
])
def test_unearned_or_malformed_commands_fail_closed(command):
    with pytest.raises(CombatSessionError):
        advance_supply(new_supply(original_supply()), command)


def test_medkit_cannot_waste_item_at_full_health():
    source = original_supply()
    first = advance_supply(new_supply(source), {"kind": "fight"})
    bought = advance_supply(first, {"kind": "buy", "item": "medkit"})
    healed = advance_supply(bought, {"kind": "use", "item": "medkit"})
    with pytest.raises(CombatSessionError, match="would not restore"):
        advance_supply(healed, {"kind": "use", "item": "medkit"})


@pytest.mark.parametrize("change", [
    lambda s: s["state"].update(currency=999999),
    lambda s: s["state"].update(hp=1000),
    lambda s: s["state"]["battles"][0].update(ward_used=True),
    lambda s: s["state"]["battles"][0]["combat"]["state"].update(currency=999),
    lambda s: s["state"]["journal"][0].update(kind="buy", item="ward"),
    lambda s: s["save"].update(parent_digest="0" * 64),
    lambda s: s.update(state_digest="0" * 64),
    lambda s: s["source"]["prices"].update(medkit=1),
])
def test_replay_rejects_tampering(change):
    saved = advance_supply(new_supply(original_supply()), {"kind": "fight"})
    corrupted = copy.deepcopy(saved)
    change(corrupted)
    with pytest.raises(CombatSessionError):
        verify_supply(corrupted)


def test_source_change_prevents_resume():
    original = original_supply()
    saved = advance_supply(new_supply(original), {"kind": "fight"})
    changed = copy.deepcopy(original)
    changed["prices"]["medkit"] = 7
    with pytest.raises(CombatSessionError, match="source mismatch"):
        finish_supply(changed, resume=saved)


def test_invalid_source_is_rejected_without_mutation():
    source = original_supply()
    source["prices"]["ward"] = True
    with pytest.raises(CombatSessionError):
        normalize_supply(source)
    source = original_supply()
    source["campaign"]["encounters"].append(copy.deepcopy(source["campaign"]["encounters"][0]))
    with pytest.raises(CombatSessionError):
        new_supply(source)


def test_package_digest_not_treated_as_authority():
    packaged = package_supply(finish_supply(original_supply()))
    for field, value in (("phase", "lost"), ("currency", 999)):
        forged = copy.deepcopy(packaged)
        forged["manifest"][field] = value
        forged["digest"] = dig({k: v for k, v in forged.items() if k != "digest"})
        with pytest.raises(CombatSessionError):
            verify_supply_package(forged)


def test_cli_end_to_end(capsys):
    source = original_supply()
    assert main(["combat-supply", "start", "--source-json", json.dumps(source)]) == 0
    initial = json.loads(capsys.readouterr().out)
    assert main(["combat-supply", "act", "--session-json", json.dumps(initial),
                 "--command-json", '{"kind":"fight"}']) == 0
    first = json.loads(capsys.readouterr().out)
    assert main(["combat-supply", "available", "--session-json", json.dumps(first)]) == 0
    choices = json.loads(capsys.readouterr().out)["actions"]
    assert {"kind": "buy", "item": "medkit"} in choices
    assert main(["combat-supply", "finish", "--session-json", json.dumps(first)]) == 0
    final = json.loads(capsys.readouterr().out)
    assert final["state"]["phase"] == "won"
    assert main(["combat-supply", "pack", "--session-json", json.dumps(final)]) == 0
    portable = json.loads(capsys.readouterr().out)
    assert main(["combat-supply", "unpack", "--package-json", json.dumps(portable)]) == 0
    assert json.loads(capsys.readouterr().out) == portable


def test_cli_duplicate_keys_and_unknown_schema(capsys):
    assert main(["combat-supply", "start", "--source-json", '{"x":1,"x":2}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
    invalid = original_supply()
    invalid["schema_version"] = SCHEMA + ".future"
    assert main(["combat-supply", "start", "--source-json", json.dumps(invalid)]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
