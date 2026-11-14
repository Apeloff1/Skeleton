"""Supply editor transactions must replay authored combat and reject drift."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.combat_campaign_supply import normalize_supply, original_supply
from skeleton.game.gameplay.combat_campaign_supply_author import (
    author_supply, original_author_demo, verify_supply_authoring,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_source_cas_preview_and_receipt_replay():
    source = original_supply()
    original = copy.deepcopy(source)
    edits = [
        {"kind": "set-price", "item": "medkit", "value": 6},
        {"kind": "set-reward", "encounter_id": "reed_watch", "value": 12},
    ]
    receipt = author_supply(source, edits, dig(normalize_supply(source)))
    assert receipt["source"]["prices"]["medkit"] == 6
    assert receipt["source"]["campaign"]["encounters"][0]["reward"] == 12
    assert receipt["preview_session"]["state"]["phase"] == "won"
    assert receipt["preview_state_digest"] == receipt["preview_session"]["state_digest"]
    assert verify_supply_authoring(source, json.loads(json.dumps(receipt))) == receipt
    assert source == original
    assert original_author_demo() == receipt


def test_stale_digest_and_partial_transaction_are_rejected():
    source = original_supply()
    before = copy.deepcopy(source)
    with pytest.raises(CombatSessionError, match="stale"):
        author_supply(source, [{"kind": "set-price", "item": "ward", "value": 4}], "0" * 64)
    with pytest.raises(CombatSessionError, match="unknown supply encounter"):
        author_supply(source, [
            {"kind": "set-price", "item": "ward", "value": 4},
            {"kind": "set-reward", "encounter_id": "missing", "value": 2},
        ], dig(normalize_supply(source)))
    assert source == before


@pytest.mark.parametrize("edits", [
    [],
    [{"kind": "set-price", "item": "medkit", "value": 8}],
    [{"kind": "set-price", "item": "wand", "value": 2}],
    [{"kind": "set-price", "item": "ward", "value": True}],
    [{"kind": "set-price", "item": "ward", "value": 0}],
    [{"kind": "set-reward", "encounter_id": "reed_watch", "value": -1}],
    [{"kind": "set-price", "item": "ward", "value": 2, "unexpected": 1}],
    [{"kind": "drop-campaign"}],
])
def test_malformed_and_noop_edits_rejected(edits):
    source = original_supply()
    with pytest.raises(CombatSessionError):
        author_supply(source, edits, dig(normalize_supply(source)))


def test_forged_receipt_and_changed_preview_fail_even_with_rehashed_digest():
    source = original_supply()
    receipt = original_author_demo()
    for mutate in (
        lambda x: x["source"]["prices"].update(ward=1),
        lambda x: x["preview_session"]["state"].update(currency=999),
        lambda x: x.update(preview_state_digest="0" * 64),
        lambda x: x["operations"][0].update(value=7),
    ):
        forged = copy.deepcopy(receipt)
        mutate(forged)
        forged["receipt"] = dig({k: v for k, v in forged.items() if k != "receipt"})
        with pytest.raises(CombatSessionError):
            verify_supply_authoring(source, forged)


def test_cli_edit_verify_and_strict_json(capsys):
    source = original_supply()
    edits = [{"kind": "set-price", "item": "ward", "value": 9}]
    assert main(["combat-supply-author", "edit", "--source-json", json.dumps(source),
                 "--operations-json", json.dumps(edits),
                 "--expected-digest", dig(normalize_supply(source))]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["source"]["prices"]["ward"] == 9
    assert main(["combat-supply-author", "verify", "--source-json", json.dumps(source),
                 "--receipt-json", json.dumps(receipt)]) == 0
    assert json.loads(capsys.readouterr().out) == receipt
    assert main(["combat-supply-author", "edit", "--source-json", json.dumps(source),
                 "--operations-json", '{"kind":1,"kind":2}',
                 "--expected-digest", dig(normalize_supply(source))]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
