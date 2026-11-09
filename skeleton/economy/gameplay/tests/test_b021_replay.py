"""B021: hash-chained command log and deterministic replay contract."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.replay import CommandLog, EconomyCommand, ReplayError, apply, replay, verify
from skeleton.economy.gameplay.tests.conftest import build_econ


def _factory():
    return build_econ(owners=())


def _log() -> CommandLog:
    log = CommandLog()
    log.extend(
        [
            EconomyCommand(0, "open_account", {"owner": "ana"}),
            EconomyCommand(0, "open_account", {"owner": "bo"}),
            EconomyCommand(1, "grant", {"faucet_id": "daily", "owner": "ana", "tick": 1}),
            EconomyCommand(2, "vendor_buy", {"owner": "ana", "item_id": "ore", "qty": 20}),
            EconomyCommand(3, "grant", {"faucet_id": "daily", "owner": "ana", "tick": 3}),  # cooldown refusal
            EconomyCommand(4, "grant", {"faucet_id": "daily", "owner": "bo", "tick": 4}),
            EconomyCommand(5, "trade", {"seller": "ana", "buyer": "bo", "item_id": "ore", "qty": 5, "price": 60}),
            EconomyCommand(6, "grant_items", {"source": "loot", "owner": "bo", "item_id": "herb", "qty": 3}),
            EconomyCommand(7, "consume_items", {"sink": "craft", "owner": "bo", "item_id": "herb", "qty": 2}),
            EconomyCommand(8, "charge", {"sink_id": "repair", "owner": "ana", "base": 100}),
        ]
    )
    return log


def test_replay_is_deterministic_including_refusals():
    log = _log()
    first = replay(_factory, log)
    second = replay(_factory, log)
    assert first == second
    assert first.refusals == 1
    assert first.outcomes[4] == {"ok": False, "error": "faucet on cooldown"}
    assert first.outcomes[6]["result"] == {"price": 60, "tax": 3, "seller_net": 57}
    assert verify(_factory, log, first.fingerprint())


def test_jsonl_round_trip_preserves_head_and_detects_edits():
    log = _log()
    text = log.to_jsonl()
    restored = CommandLog.from_jsonl(text, expected_head=log.head)
    assert restored.head == log.head
    tampered = text.replace('"price":60', '"price":6')
    with pytest.raises(ReplayError, match="head mismatch"):
        CommandLog.from_jsonl(tampered, expected_head=log.head)
    lines = text.splitlines()
    lines[0], lines[1] = lines[1], lines[0]  # same tick, swapped order: chain head changes
    with pytest.raises(ReplayError):
        CommandLog.from_jsonl("\n".join(lines), expected_head=log.head)


def test_fingerprint_changes_when_outcome_changes():
    log = _log()
    base = replay(_factory, log).fingerprint()
    log2 = _log()
    log2.append(EconomyCommand(9, "charge", {"sink_id": "upkeep", "owner": "bo"}))
    assert replay(_factory, log2).fingerprint() != base
    assert not verify(_factory, log2, base)


def test_commands_are_validated():
    with pytest.raises(ReplayError, match="unknown op"):
        EconomyCommand(0, "mint_anything", {})
    with pytest.raises(ReplayError, match="unexpected args"):
        EconomyCommand(0, "grant", {"faucet_id": "daily", "owner": "ana", "tick": 0, "amount": 9})
    with pytest.raises(ReplayError, match="str or int"):
        EconomyCommand(0, "bind", {"owner": "ana", "item_id": "ore", "qty": True})
    log = CommandLog()
    log.append(EconomyCommand(5, "open_account", {"owner": "ana"}))
    with pytest.raises(ReplayError, match="backwards"):
        log.append(EconomyCommand(4, "open_account", {"owner": "bo"}))


def test_apply_reports_missing_args_without_raising():
    econ = build_econ()
    out = apply(econ, EconomyCommand(0, "trade", {"seller": "ana", "buyer": "bo"}))
    assert out["ok"] is False and "missing" in out["error"]
