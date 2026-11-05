"""Merchant-hours vertical: gameplay, editor, portable custody and CLI."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_market_hours import (
    _advance, cli, edit_hours, export_hours, import_hours, merchant_board,
    new_hours, normalize_hours, original_hours, resume_hours, simulate_hours,
    verify_hours, verify_merchant_board,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_original_campaign_is_playable_and_exportable():
    source, actions = original_hours()
    terminal = simulate_hours(source, actions)
    assert terminal["state"]["phase"] == "won"
    assert terminal["state"]["market"]["state"]["credits"] == 1
    assert terminal["state"]["purchases_by_merchant"] == {"gate_trader": 1}
    assert import_hours(json.loads(json.dumps(export_hours(terminal)))) == terminal
    assert verify_hours(json.loads(json.dumps(terminal))) == terminal


@pytest.mark.parametrize("split", [0, 1, 4, 5, 6, 7, 9, 11])
def test_resume_at_each_boundary(split):
    source, actions = original_hours()
    checkpoint = simulate_hours(source, actions[:split])
    assert resume_hours(checkpoint, actions[split:]) == simulate_hours(source, actions)


def test_opening_window_is_enforced_at_purchase_tick():
    source, actions = original_hours()
    source["windows"][0]["opens_at"] = 7
    checkpoint = simulate_hours(source, actions[:5])
    before = copy.deepcopy(checkpoint)
    with pytest.raises(SceneTravelError, match="closed"):
        _advance(checkpoint, actions[5])
    assert checkpoint == before
    board = merchant_board(checkpoint)
    assert board["merchants"][0]["open"] is False
    assert board["merchants"][0]["next_open_tick"] == 7
    assert verify_merchant_board(checkpoint, board) == board


def test_reputation_gate_cannot_be_bypassed_by_currency():
    source, actions = original_hours()
    source["windows"][0]["min_reputation"] = 1
    checkpoint = simulate_hours(source, actions[:5])
    assert checkpoint["state"]["market"]["state"]["credits"] == 3
    with pytest.raises(SceneTravelError, match="reputation"):
        _advance(checkpoint, actions[5])


def test_board_reflects_real_canonical_position_stock_and_credits():
    source, actions = original_hours()
    start = new_hours(source)
    assert not merchant_board(start)["merchants"][0]["offers"][0]["purchasable"]
    checkpoint = simulate_hours(source, actions[:5])
    offer = merchant_board(checkpoint)["merchants"][0]["offers"][0]
    assert offer["purchasable"] and offer["remaining_stock"] == 1
    bought = _advance(checkpoint, actions[5])
    assert not merchant_board(bought)["merchants"][0]["offers"][0]["purchasable"]
    assert merchant_board(bought)["merchants"][0]["offers"][0]["remaining_stock"] == 0


@pytest.mark.parametrize("change", [
    lambda s: s["windows"][0].update(opens_at=0),
    lambda s: s["windows"][0].update(opens_at=True),
    lambda s: s["windows"][0].update(closes_at=0),
    lambda s: s["windows"][0].update(min_reputation=-1),
    lambda s: s["windows"][0].update(market_id="forged"),
    lambda s: s.update(windows=[]),
    lambda s: s.update(schema_version="future"),
])
def test_invalid_authored_windows_fail_closed(change):
    source, _ = original_hours()
    change(source)
    with pytest.raises(SceneTravelError):
        normalize_hours(source)


def test_overlapping_windows_and_missing_merchant_rejected():
    source, _ = original_hours()
    source["windows"].append({
        "market_id": "gate_trader", "opens_at": 5,
        "closes_at": 10, "min_reputation": 0,
    })
    with pytest.raises(SceneTravelError, match="overlapping"):
        normalize_hours(source)


def test_editor_is_transactional_and_keeps_market_source():
    source, _ = original_hours()
    before = copy.deepcopy(source)
    edited = edit_hours(source, [
        {"kind": "remove", "market_id": "gate_trader", "opens_at": 1},
        {"kind": "add", "market_id": "gate_trader", "opens_at": 5,
         "closes_at": 10, "min_reputation": 0},
    ])
    assert source == before
    assert edited["market_source"] == normalize_hours(source)["market_source"]
    assert edited["windows"][0]["opens_at"] == 5
    with pytest.raises(SceneTravelError):
        edit_hours(source, [{"kind": "remove", "market_id": "gate_trader",
                             "opens_at": 1}])
    assert source == before


@pytest.mark.parametrize("mutate", [
    lambda s: s["state"].update(purchases_by_merchant={"gate_trader": 999}),
    lambda s: s["state"]["market"]["state"].update(credits=999),
    lambda s: s["journal"][0].update(receipt="0" * 64),
    lambda s: s["save"].update(tick=999),
    lambda s: s.update(source_digest="0" * 64),
])
def test_forged_session_fails_even_if_checksums_are_recomputed(mutate):
    source, actions = original_hours()
    bad = copy.deepcopy(simulate_hours(source, actions))
    mutate(bad)
    with pytest.raises(SceneTravelError):
        verify_hours(bad)


def test_portable_tamper_rejected_and_board_witness_not_authority():
    source, actions = original_hours()
    checkpoint = simulate_hours(source, actions[:5])
    bundle = export_hours(checkpoint)
    for field in ("checksum", "source_digest", "state_digest"):
        bad = copy.deepcopy(bundle)
        bad[field] = "0" * 64
        with pytest.raises(SceneTravelError):
            import_hours(bad)
    board = merchant_board(checkpoint)
    board["merchants"][0]["offers"][0]["purchasable"] = False
    with pytest.raises(SceneTravelError, match="witness"):
        verify_merchant_board(checkpoint, board)


def test_rejected_batch_preserves_original_checkpoint():
    source, actions = original_hours()
    checkpoint = simulate_hours(source, actions[:5])
    before = copy.deepcopy(checkpoint)
    with pytest.raises(SceneTravelError):
        resume_hours(checkpoint, [actions[5], actions[5]])
    assert checkpoint == before


def test_cli_reachable_from_root_and_duplicate_json_denied(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-hours", "demo"]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["state"]["phase"] == "won"
    assert cli(["export", "--session-json", json.dumps(saved)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == saved
    assert cli(["simulate", "--source-json", '{"x":1,"x":2}',
                "--actions-json", "[]"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
