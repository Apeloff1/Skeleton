"""B024: untrusted player intents -> validated, authorised, deduped, rate-limited commands."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.intents import MAX_QTY, IntentError, IntentGate
from skeleton.economy.gameplay.replay import apply
from skeleton.economy.gameplay.tests.conftest import build_econ


def test_valid_intent_becomes_replayable_command():
    gate = IntentGate()
    cmd = gate.parse("ana", {"op": "vendor_buy", "item_id": "ore", "qty": 3, "nonce": "abcdefgh1"}, tick=7)
    assert cmd.op == "vendor_buy" and cmd.tick == 7
    assert dict(cmd.args) == {"item_id": "ore", "owner": "ana", "qty": 3}
    econ = build_econ()
    econ.grant("daily", "ana", tick=0)
    assert apply(econ, cmd) == {"ok": True, "result": 30}


def test_grant_tick_comes_from_server_not_client():
    gate = IntentGate()
    cmd = gate.parse("ana", {"op": "grant", "faucet_id": "daily", "nonce": "nonce-0001"}, tick=42)
    assert cmd.args["tick"] == 42
    with pytest.raises(IntentError, match="unknown fields"):
        gate.parse("ana", {"op": "grant", "faucet_id": "daily", "tick": 1, "nonce": "nonce-0002"}, tick=43)


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"op": "trade", "nonce": "nonce-0001"}, "op not allowed"),
        ({"op": "grant_items", "nonce": "nonce-0001"}, "op not allowed"),
        ({"op": "vendor_buy", "item_id": "ore", "nonce": "x"}, "invalid nonce"),
        ({"op": "vendor_buy", "item_id": "ore", "qty": True, "nonce": "nonce-0001"}, "integer"),
        ({"op": "vendor_buy", "item_id": "ore", "qty": 0, "nonce": "nonce-0001"}, "out of range"),
        ({"op": "vendor_buy", "item_id": "ore", "qty": MAX_QTY + 1, "nonce": "nonce-0001"}, "out of range"),
        ({"op": "vendor_buy", "item_id": "Ore;drop", "nonce": "nonce-0001"}, "invalid item_id"),
        ({"op": "vendor_buy", "nonce": "nonce-0001"}, "missing item_id"),
        ({"op": "vendor_buy", "item_id": "ore", "owner": "bo", "nonce": "nonce-0001"}, "session owner"),
        ({"op": "move_items", "src": "bo", "dst": "ana", "item_id": "ore", "nonce": "nonce-0001"}, "session owner"),
        ({"op": "charge", "sink_id": "repair", "base": -1, "nonce": "nonce-0001"}, "out of range"),
    ],
)
def test_hostile_payloads_refused(payload, message):
    with pytest.raises(IntentError, match=message):
        IntentGate().parse("ana", payload, tick=0)


def test_payload_must_be_mapping():
    with pytest.raises(IntentError, match="object"):
        IntentGate().parse("ana", ["op", "grant"], tick=0)  # type: ignore[arg-type]


def test_duplicate_nonce_is_idempotent_and_free():
    gate = IntentGate(capacity=2, refill_per_tick=0)
    payload = {"op": "bind", "item_id": "ore", "nonce": "same-nonce-1"}
    assert gate.parse("ana", payload, tick=0) is not None
    assert gate.parse("ana", payload, tick=0) is None
    assert gate.parse("bo", payload, tick=0) is not None  # nonces are per owner
    assert gate.parse("ana", {**payload, "nonce": "other-nonce"}, tick=0) is not None


def test_token_bucket_rate_limits_and_refills():
    gate = IntentGate(capacity=2, refill_per_tick=1)
    gate.parse("ana", {"op": "bind", "item_id": "ore", "nonce": "n-000001"}, tick=0)
    gate.parse("ana", {"op": "bind", "item_id": "ore", "nonce": "n-000002"}, tick=0)
    with pytest.raises(IntentError, match="rate limited"):
        gate.parse("ana", {"op": "bind", "item_id": "ore", "nonce": "n-000003"}, tick=0)
    # the refused nonce was not burned, so the client may retry it later
    assert gate.parse("ana", {"op": "bind", "item_id": "ore", "nonce": "n-000003"}, tick=1) is not None
    with pytest.raises(IntentError, match="backwards"):
        gate.parse("ana", {"op": "bind", "item_id": "ore", "nonce": "n-000004"}, tick=0)


def test_nonce_memory_is_bounded():
    gate = IntentGate(capacity=100, max_nonces=2)
    for i in range(3):
        gate.parse("ana", {"op": "bind", "item_id": "ore", "nonce": f"nonce-{i:04d}"}, tick=0)
    assert len(gate._nonces) == 2
