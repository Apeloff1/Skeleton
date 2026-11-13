"""Deterministic economy audit, tamper detection and branch comparisons."""
from __future__ import annotations

import copy
import json
import pytest

from skeleton.game.gameplay.arena_expedition import (
    new_expedition, original_expedition, resume_expedition, simulate_expedition,
)
from skeleton.game.gameplay.arena_expedition_economy import (
    audit_expedition, cli, compare_expeditions, verify_audit,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def _saved():
    return simulate_expedition(original_expedition(), [
        {"kind": "fight"}, {"kind": "buy", "item_id": "tide_tonic"},
        {"kind": "use", "item_id": "tide_tonic"}, {"kind": "fight"},
    ])


def test_earned_reward_spend_and_stock_reconcile():
    report = audit_expedition(_saved())
    assert report["phase"] == "won"
    assert (report["total_earned"], report["total_spent"], report["balance"]) == (30, 5, 25)
    assert report["shop_remaining"] == {"tide_tonic": 1}
    assert report["inventory"] == {}
    assert [e["kind"] for e in report["timeline"]] == ["fight", "buy", "use", "fight"]
    assert [e["earned"] for e in report["timeline"]] == [10, 0, 0, 20]
    assert report["timeline"][1]["inventory_delta"] == {"tide_tonic": 1}
    assert report["timeline"][2]["inventory_delta"] == {"tide_tonic": -1}
    assert verify_audit(json.loads(json.dumps(report)), session=_saved()) == report


def test_new_save_is_zero_balance_and_deterministic():
    empty = new_expedition(original_expedition())
    result = audit_expedition(empty)
    assert result["total_earned"] == result["total_spent"] == result["balance"] == 0
    assert result["timeline"] == []
    assert audit_expedition(_saved()) == audit_expedition(json.loads(json.dumps(_saved())))


@pytest.mark.parametrize("field,value", [
    ("total_earned", 100000), ("balance", -1),
    ("checksum", "0" * 64), ("source_digest", "0" * 64),
    ("shop_remaining", {"tide_tonic": 999}),
    ("inventory", {"tide_tonic": 99}),
])
def test_forged_economy_receipt_rejected(field, value):
    saved = _saved()
    bad = audit_expedition(saved)
    bad[field] = value
    with pytest.raises(CombatSessionError):
        verify_audit(bad, session=saved)


def test_forged_save_and_nested_rewards_rejected():
    for target in ("currency", "nested", "receipt"):
        bad = copy.deepcopy(_saved())
        if target == "currency":
            bad["state"]["currency"] = 100000
        elif target == "nested":
            bad["state"]["arenas"][0]["reward"] = 9999
        else:
            bad["journal"][0]["receipt"] = "0" * 64
        with pytest.raises(CombatSessionError):
            audit_expedition(bad)


def test_two_branches_have_separate_earned_and_spent_balances():
    start = simulate_expedition(original_expedition(), [{"kind": "fight"}])
    spent = resume_expedition(start, [{"kind": "buy", "item_id": "tide_tonic"}])
    report = compare_expeditions(spent, start)
    assert report["common_action_prefix"] == 1
    assert report["left"]["balance"] == 5
    assert report["right"]["balance"] == 10
    assert report["left"]["spent"] == 5
    assert report["right"]["spent"] == 0
    assert report["same_state"] is False
    assert compare_expeditions(start, start)["same_state"] is True


def test_different_source_comparison_rejected():
    first = new_expedition(original_expedition())
    source = original_expedition()
    source["expedition_id"] = "another_original"
    with pytest.raises(CombatSessionError, match="different"):
        compare_expeditions(first, new_expedition(source))


def test_cli_and_canonical_main_dispatch(capsys):
    assert cli(["demo"]) == 0
    demo = json.loads(capsys.readouterr().out)
    assert demo["balance"] == 25
    saved = _saved()
    assert cli(["audit", "--session-json", json.dumps(saved)]) == 0
    assert json.loads(capsys.readouterr().out) == demo
    assert cli(["verify", "--session-json", json.dumps(saved),
                "--audit-json", json.dumps(demo)]) == 0
    assert json.loads(capsys.readouterr().out) == demo
    from skeleton.__main__ import main
    assert main(["combat-expedition-audit", "audit", "--session-json",
                 json.dumps(saved)]) == 0
    assert json.loads(capsys.readouterr().out) == demo


def test_cli_rejects_invalid_save(capsys):
    assert cli(["audit", "--session-json", '{"bad":true}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
