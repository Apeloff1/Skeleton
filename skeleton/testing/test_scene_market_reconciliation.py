"""Append-only source-bound market checkpoint reconciliation tests."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import (
    _advance, cli, original_market, simulate_market,
)
from skeleton.game.gameplay.scene_market_reconciliation import reconcile_market
from skeleton.game.gameplay.scene_travel import SceneTravelError


@pytest.mark.parametrize("split", [0, 1, 4, 5, 6, 7, 8, 9, 10])
def test_market_checkpoint_reconciliation_replay(split):
    source, actions = original_market()
    before = simulate_market(source, actions[:split])
    after = simulate_market(source, actions)
    report = reconcile_market(before, after)
    assert report["actions_applied"] == len(actions) - split
    assert report["credits_delta"] == (after["state"]["credits"] -
                                       before["state"]["credits"])
    assert report["reputation_delta"] == (after["state"]["reputation"] -
                                          before["state"]["reputation"])
    assert report["appended_receipts"] == [
        event["receipt"] for event in after["journal"][split:]
    ]
    assert report["checksum"] == dig({
        key: value for key, value in report.items() if key != "checksum"
    })


def test_market_checkpoint_self_reconciliation_is_identity():
    source, actions = original_market()
    session = simulate_market(source, actions[:6])
    report = reconcile_market(session, json.loads(json.dumps(session)))
    assert report["actions_applied"] == 0
    assert report["credits_delta"] == 0
    assert report["goods_delta"] == {}
    assert report["new_deliveries"] == []
    assert report["from_state_digest"] == report["to_state_digest"]


def test_market_checkpoint_purchase_and_crafting_conservation():
    source, actions = original_market()
    before = simulate_market(source, actions[:5])
    after = simulate_market(source, actions[:8])
    report = reconcile_market(before, after)
    assert report["credits_delta"] == -2
    assert report["credits_spent_delta"] == 2
    assert report["purchases_delta"] == {"copper_badge": 1}
    assert report["crafted_delta"] == {"seal_press": 1}
    assert report["goods_delta"] == {"seal": 1}


def test_market_checkpoint_rejects_reversed_or_divergent_history():
    source, actions = original_market()
    start = simulate_market(source, actions[:5])
    purchased = _advance(start, {"kind": "buy", "offer_id": "copper_badge"})
    # A legal alternative action produces a different canonical journal.
    moved = _advance(start, {"kind": "tile", "action": {
        "kind": "move", "direction": "east",
    }})
    with pytest.raises(SceneTravelError, match="append-only"):
        reconcile_market(purchased, moved)
    with pytest.raises(SceneTravelError, match="append-only"):
        reconcile_market(purchased, start)


def test_market_checkpoint_rejects_changed_source_and_forged_state():
    source, actions = original_market()
    before = simulate_market(source, actions[:5])
    changed = copy.deepcopy(source)
    changed["markets"][0]["offers"][0]["price"] = 3
    after = simulate_market(changed, actions[:5])
    with pytest.raises(SceneTravelError, match="source mismatch"):
        reconcile_market(before, after)
    forged = copy.deepcopy(simulate_market(source, actions))
    forged["state"]["credits"] += 100
    with pytest.raises(SceneTravelError):
        reconcile_market(before, forged)


def test_market_checkpoint_cli_user_reachable(capsys):
    from skeleton.__main__ import main
    source, actions = original_market()
    before = simulate_market(source, actions[:5])
    after = simulate_market(source, actions)
    args = ["ledger-reconcile", "--before-json", json.dumps(before),
            "--after-json", json.dumps(after)]
    assert main(["scene-market", *args]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["credits_delta"] == -2
    assert report["actions_applied"] == len(actions) - 5
    assert cli(["ledger-reconcile", "--before-json", "{}",
                "--after-json", json.dumps(after)]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
