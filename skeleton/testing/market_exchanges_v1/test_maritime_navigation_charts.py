"""Accounting and replay invariants for maritime_navigation_charts."""
from __future__ import annotations

import pytest

from skeleton.forge.market_exchanges_v1.maritime_navigation_charts import (
    Ledger, CAPACITY, BASE_PRICE, MAX_QUANTITY, MAX_RECEIPTS,
    quote, transact, snapshot, replay
)


def command(identity="t1", side="buy", quantity=2, version=0, tick=1):
    return {
        "id": identity, "side": side, "quantity": quantity,
        "expected_version": version, "tick": tick,
    }


def test_initial_market_is_valid():
    state = Ledger()
    view = snapshot(state)
    assert view["market_id"] == "maritime_navigation_charts"
    assert 0 <= view["stock"] <= CAPACITY
    assert view["buy_unit_price"] >= BASE_PRICE


def test_quote_is_deterministic():
    state = Ledger()
    assert quote("buy", 1, state) == quote("buy", 1, state)
    assert quote("sell", 1, state) > 0
    assert quote("buy", 1, state) >= quote("sell", 1, state)


def test_buy_conserves_in_world_credits_and_units():
    original = Ledger()
    updated, receipt = transact(original, command())
    assert receipt.accepted
    assert updated.stock + updated.holdings == original.stock + original.holdings
    assert updated.wallet + updated.treasury == original.wallet + original.treasury
    assert receipt.total == receipt.unit_price * receipt.quantity


def test_sell_conserves_credits_and_units():
    state, _ = transact(Ledger(), command())
    updated, receipt = transact(state, command("t2", "sell", 1, 1, 2))
    assert receipt.accepted
    assert updated.stock + updated.holdings == state.stock + state.holdings
    assert updated.wallet + updated.treasury == state.wallet + state.treasury


def test_duplicate_replay_is_rejected():
    state, _ = transact(Ledger(), command())
    same, receipt = transact(state, command("t1", "sell", 1, 1, 2))
    assert same is state
    assert receipt.reason == "duplicate-identity"


def test_stale_version_rejects_without_mutation():
    state, _ = transact(Ledger(), command())
    same, receipt = transact(state, command("t2", version=0, tick=2))
    assert same is state
    assert receipt.reason == "stale-version"


def test_nonmonotonic_clock_rejects():
    state, _ = transact(Ledger(), command())
    same, receipt = transact(state, command("t2", version=1, tick=1))
    assert same is state
    assert receipt.reason == "nonmonotonic-tick"


def test_insufficient_stock_rejected():
    state = Ledger(stock=0)
    unchanged, receipt = transact(state, command())
    assert unchanged is state
    assert receipt.reason == "insufficient-stock"


def test_insufficient_wallet_rejected():
    state = Ledger(wallet=0)
    unchanged, receipt = transact(state, command())
    assert unchanged is state
    assert receipt.reason == "insufficient-wallet"


def test_insufficient_holdings_rejected():
    state = Ledger(holdings=0)
    unchanged, receipt = transact(state, command(side="sell"))
    assert unchanged is state
    assert receipt.reason == "insufficient-holdings"


def test_insufficient_treasury_rejected():
    state = Ledger(holdings=5, treasury=0)
    unchanged, receipt = transact(state, command(side="sell"))
    assert unchanged is state
    assert receipt.reason == "insufficient-treasury"


def test_storage_capacity_rejected():
    state = Ledger(stock=CAPACITY, holdings=5)
    unchanged, receipt = transact(state, command(side="sell"))
    assert unchanged is state
    assert receipt.reason == "storage-capacity"


@pytest.mark.parametrize("bad", [None, True, 0, -1, 1.5, MAX_QUANTITY + 1])
def test_invalid_quantities_rejected(bad):
    with pytest.raises(ValueError):
        transact(Ledger(), command(quantity=bad))


@pytest.mark.parametrize("side", ["", "refund", "admin", None, True])
def test_unknown_sides_rejected(side):
    with pytest.raises(ValueError):
        transact(Ledger(), command(side=side))


def test_unknown_command_fields_rejected():
    with pytest.raises(ValueError):
        transact(Ledger(), {**command(), "override": True})


def test_invalid_ledger_rejected():
    with pytest.raises(ValueError):
        Ledger(stock=CAPACITY + 1)
    with pytest.raises(ValueError):
        Ledger(treasury=-1)
    with pytest.raises(ValueError):
        Ledger(wallet=True)
    with pytest.raises(ValueError):
        Ledger(tick=-1)
    with pytest.raises(ValueError):
        Ledger(receipts=frozenset({""}))


def test_pure_replay_is_stable():
    commands = [command("a", "buy", 2, 0, 1), command("b", "sell", 1, 1, 2)]
    assert replay(commands) == replay(commands)
    state, receipts = replay(commands)
    assert state.version == 2
    assert all(receipt.accepted for receipt in receipts)


def test_batch_capacity_is_bounded():
    with pytest.raises(ValueError):
        replay([command()] * (MAX_RECEIPTS + 1))
