"""Market source edits are atomic, source-leased and preview-replayable."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import (
    normalize_market, original_market, simulate_market,
)
from skeleton.game.gameplay.scene_market_author import (
    cli, edit_market, verify_market_edit,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def _source():
    source, actions = original_market()
    return source, actions, dig(normalize_market(source))


def test_editor_changes_price_and_replays_winning_preview():
    source, actions, digest = _source()
    receipt = edit_market(source, [
        {"kind": "set_price", "offer_id": "copper_badge", "value": 3},
    ], digest, actions)
    assert receipt["preview_phase"] == "won"
    assert receipt["source"]["markets"][0]["offers"][0]["price"] == 3
    assert receipt["preview_state_digest"] == (
        simulate_market(receipt["source"], actions)["state_digest"]
    )
    assert verify_market_edit(json.loads(json.dumps(receipt))) == receipt
    assert source["markets"][0]["offers"][0]["price"] == 2


@pytest.mark.parametrize("op", [
    {"kind": "set_price", "offer_id": "missing", "value": 1},
    {"kind": "set_stock", "offer_id": "copper_badge", "value": 0},
    {"kind": "set_coin", "pickup": "quay:unearned", "value": 3},
    {"kind": "set_recipe_input", "recipe_id": "seal_press",
     "item_id": "forged", "value": 1},
    {"kind": "set_delivery_reputation", "delivery_id": "unknown", "value": 2},
    {"kind": "set_price", "offer_id": "copper_badge", "value": True},
    {"kind": "unknown", "offer_id": "copper_badge", "value": 1},
])
def test_invalid_edits_fail_closed(op):
    source, actions, digest = _source()
    original = copy.deepcopy(source)
    with pytest.raises(SceneTravelError):
        edit_market(source, [op], digest, actions)
    assert source == original


def test_editor_rejects_stale_digest_and_noop():
    source, _, digest = _source()
    with pytest.raises(SceneTravelError, match="changed"):
        edit_market(source, [
            {"kind": "set_price", "offer_id": "copper_badge", "value": 3},
        ], "0" * 64)
    with pytest.raises(SceneTravelError, match="no effect"):
        edit_market(source, [
            {"kind": "set_price", "offer_id": "copper_badge", "value": 2},
        ], digest)


def test_edit_batch_rolls_back_if_preview_cannot_play():
    source, actions, digest = _source()
    before = copy.deepcopy(source)
    with pytest.raises(SceneTravelError):
        edit_market(source, [
            {"kind": "set_price", "offer_id": "copper_badge", "value": 4},
        ], digest, actions)
    assert source == before


def test_editor_receipt_tamper_and_reordered_actions_rejected():
    source, actions, digest = _source()
    receipt = edit_market(source, [
        {"kind": "set_coin", "pickup": "quay:find_key", "value": 4},
    ], digest, actions)
    for key, value in (
        ("checksum", "0" * 64),
        ("source_digest", "0" * 64),
        ("preview_phase", "lost"),
    ):
        bad = copy.deepcopy(receipt)
        bad[key] = value
        with pytest.raises(SceneTravelError):
            verify_market_edit(bad)


def test_main_cli_demo_and_editor_verify(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-author", "demo"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["preview_phase"] == "won"
    assert cli(["verify", "--receipt-json", json.dumps(receipt)]) == 0
    assert json.loads(capsys.readouterr().out) == receipt
    assert cli(["edit", "--source-json", '{"x":1,"x":2}',
                "--expected-source-digest", "0" * 64,
                "--operations-json", "[]"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
