"""Transactional authoring: canonical source -> edits -> playable preview."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather_market import (
    normalize_market, original_market, resume_market, new_market,
)
from skeleton.game.gameplay.scene_weather_market_author import (
    edit_market, original_author_demo, verify_market_edit,
)


def test_atomic_market_authoring_and_real_playable_preview():
    source, actions = original_market()
    before = copy.deepcopy(source)
    edited = edit_market(
        source, [
            {"kind": "set-commission", "delivery_id": "gate_supply", "value": 2000},
            {"kind": "set-reputation", "delivery_id": "lantern_supply", "value": 7},
        ], dig(normalize_market(source)), actions=actions,
    )
    assert source == before
    assert edited["before_digest"] != edited["after_digest"]
    assert edited["source"]["contracts"][0]["commission_bps"] == 2000
    assert edited["preview_session"]["state"]["phase"] == "won"
    assert edited["preview_session"]["state"]["gross"] == 30
    assert edited["preview_session"]["state"]["net"] == 27
    assert edited["preview_session"] == resume_market(
        new_market(edited["source"]), actions,
    )
    assert verify_market_edit(source, json.loads(json.dumps(edited))) == edited


def test_no_preview_actions_creates_durable_initial_save():
    source, _ = original_market()
    receipt = edit_market(
        source,
        [{"kind": "set-early-threshold", "delivery_id": "gate_supply",
          "value": 2}],
        dig(normalize_market(source)),
    )
    assert receipt["preview_session"]["state"]["journal"] == []
    assert receipt["preview_session"]["state"]["gross"] == 0
    assert verify_market_edit(source, receipt) == receipt


@pytest.mark.parametrize("edits", [
    [],
    [{"kind": "set-commission", "delivery_id": "unknown", "value": 100}],
    [{"kind": "set-commission", "delivery_id": "gate_supply", "value": True}],
    [{"kind": "set-commission", "delivery_id": "gate_supply", "value": 5001}],
    [{"kind": "set-reputation", "delivery_id": "gate_supply", "value": 101}],
    [{"kind": "set-early-threshold", "delivery_id": "gate_supply", "value": 0}],
    [{"kind": "unknown", "delivery_id": "gate_supply", "value": 1}],
    [{"kind": "set-commission", "delivery_id": "gate_supply", "value": 1000}],
    [{"kind": "set-commission", "delivery_id": "gate_supply", "value": 2000},
     {"kind": "set-commission", "delivery_id": "gate_supply", "value": 3000}],
])
def test_invalid_or_noop_edits_fail_closed(edits):
    source, _ = original_market()
    with pytest.raises(SceneTravelError):
        edit_market(source, edits, dig(normalize_market(source)))


def test_stale_source_digest_blocks_transaction():
    source, _ = original_market()
    with pytest.raises(SceneTravelError, match="stale"):
        edit_market(source, [
            {"kind": "set-commission", "delivery_id": "gate_supply", "value": 2000},
        ], "0" * 64)


def test_rehashed_receipt_forgery_still_fails_source_replay():
    source, receipt = original_author_demo()
    forged = copy.deepcopy(receipt)
    forged["preview_session"]["state"]["net"] += 100
    forged["receipt"] = dig({k: v for k, v in forged.items() if k != "receipt"})
    with pytest.raises(SceneTravelError):
        verify_market_edit(source, forged)


def test_changed_source_rejected_even_when_receipt_was_valid():
    source, receipt = original_author_demo()
    changed = copy.deepcopy(source)
    changed["contracts"][0]["commission_bps"] = 200
    with pytest.raises(SceneTravelError, match="stale"):
        verify_market_edit(changed, receipt)


def _run(capsys, *args):
    status = main(list(args))
    result = capsys.readouterr()
    return status, json.loads(result.out or result.err)


def test_main_cli_author_demo_edit_verify_and_preview(capsys):
    source, actions = original_market()
    status, demo = _run(capsys, "weather-market-author", "demo")
    assert status == 0 and demo["preview_session"]["state"]["phase"] == "won"
    status, edited = _run(
        capsys, "weather-market-author", "edit",
        "--source-json", json.dumps(source),
        "--operations-json", json.dumps([
            {"kind": "set-commission", "delivery_id": "gate_supply", "value": 2000},
        ]),
        "--expected-digest", dig(normalize_market(source)),
        "--actions-json", json.dumps(actions),
    )
    assert status == 0 and edited == demo
    status, verified = _run(
        capsys, "weather-market-author", "verify",
        "--source-json", json.dumps(source),
        "--receipt-json", json.dumps(edited),
    )
    assert status == 0 and verified == edited


def test_main_cli_invalid_digest_has_no_partial_export(capsys):
    source, _ = original_market()
    status, error = _run(
        capsys, "weather-market-author", "edit",
        "--source-json", json.dumps(source),
        "--operations-json", json.dumps([
            {"kind": "set-commission", "delivery_id": "gate_supply", "value": 2000},
        ]),
        "--expected-digest", "0" * 64,
    )
    assert status == 2 and error["ok"] is False
