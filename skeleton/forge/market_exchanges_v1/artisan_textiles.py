"""Deterministic market exchange: textiles in artisan.

All values are discrete in-world units, not fiat, crypto, or player accounts.
The caller authenticates the actor and persists event receipts atomically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA = "skeleton.market_exchange.v1"
MARKET_ID = "artisan_textiles"
DOMAIN = "artisan"
COMMODITY = "textiles"
BASE_PRICE = 23
MARKUP_BPS = 105
TARIFF = 6
CAPACITY = 122
INITIAL_STOCK = 58
INITIAL_CREDITS = 4178
MAX_QUANTITY = 32
MAX_RECEIPTS = 4096


@dataclass(frozen=True, slots=True)
class Ledger:
    stock: int = INITIAL_STOCK
    treasury: int = INITIAL_CREDITS
    holdings: int = 0
    wallet: int = INITIAL_CREDITS
    version: int = 0
    tick: int = 0
    receipts: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if type(self.stock) is not int or not 0 <= self.stock <= CAPACITY:
            raise ValueError("invalid-stock")
        for key in ("treasury", "holdings", "wallet", "version", "tick"):
            value = getattr(self, key)
            if type(value) is not int or value < 0 or value > 2**63 - 1:
                raise ValueError("invalid-" + key)
        if type(self.receipts) is not frozenset or len(self.receipts) > MAX_RECEIPTS:
            raise ValueError("invalid-receipt-ledger")
        if any(type(key) is not str or not 1 <= len(key) <= 128 for key in self.receipts):
            raise ValueError("invalid-receipt-id")


@dataclass(frozen=True, slots=True)
class ExchangeReceipt:
    id: str
    accepted: bool
    reason: str
    quantity: int
    unit_price: int
    total: int
    before_version: int
    after_version: int


def quote(side: str, quantity: int, state: Ledger) -> int:
    """Deterministic total quote without floating point or mutation."""
    if type(state) is not Ledger:
        raise TypeError("invalid-ledger")
    if side not in ("buy", "sell") or type(side) is not str:
        raise ValueError("invalid-side")
    if type(quantity) is not int or not 1 <= quantity <= MAX_QUANTITY:
        raise ValueError("invalid-quantity")
    scarcity = (CAPACITY - state.stock) // 10
    price = BASE_PRICE + scarcity + TARIFF
    if side == "buy":
        price = (price * MARKUP_BPS + 99) // 100
    else:
        price = max(1, (price * (200 - MARKUP_BPS)) // 100)
    return price


def _command(raw: dict[str, Any]) -> tuple[str, str, int, int, int]:
    if type(raw) is not dict or set(raw) != {
        "id", "side", "quantity", "expected_version", "tick"
    }:
        raise ValueError("invalid-command-shape")
    identity, side, qty, version, tick = (
        raw["id"], raw["side"], raw["quantity"],
        raw["expected_version"], raw["tick"]
    )
    if type(identity) is not str or not 1 <= len(identity) <= 128:
        raise ValueError("invalid-id")
    if type(side) is not str or side not in ("buy", "sell"):
        raise ValueError("invalid-side")
    if type(qty) is not int or not 1 <= qty <= MAX_QUANTITY:
        raise ValueError("invalid-quantity")
    if type(version) is not int or version < 0:
        raise ValueError("invalid-expected-version")
    if type(tick) is not int or tick < 0:
        raise ValueError("invalid-tick")
    return identity, side, qty, version, tick


def transact(state: Ledger, command: dict[str, Any]) -> tuple[Ledger, ExchangeReceipt]:
    if type(state) is not Ledger:
        raise TypeError("invalid-ledger")
    identity, side, quantity, version, tick = _command(command)

    def reject(reason: str) -> tuple[Ledger, ExchangeReceipt]:
        return state, ExchangeReceipt(
            identity, False, reason, quantity, 0, 0,
            state.version, state.version,
        )

    if identity in state.receipts:
        return reject("duplicate-identity")
    if version != state.version:
        return reject("stale-version")
    if tick <= state.tick:
        return reject("nonmonotonic-tick")
    if len(state.receipts) == MAX_RECEIPTS:
        return reject("receipt-capacity")

    unit = quote(side, quantity, state)
    total = unit * quantity
    if side == "buy":
        if state.stock < quantity:
            return reject("insufficient-stock")
        if state.wallet < total:
            return reject("insufficient-wallet")
        updated = Ledger(
            state.stock - quantity,
            state.treasury + total,
            state.holdings + quantity,
            state.wallet - total,
            version + 1, tick, state.receipts | {identity},
        )
    else:
        if state.holdings < quantity:
            return reject("insufficient-holdings")
        if state.treasury < total:
            return reject("insufficient-treasury")
        if state.stock + quantity > CAPACITY:
            return reject("storage-capacity")
        updated = Ledger(
            state.stock + quantity,
            state.treasury - total,
            state.holdings - quantity,
            state.wallet + total,
            version + 1, tick, state.receipts | {identity},
        )

    return updated, ExchangeReceipt(
        identity, True, "accepted", quantity, unit, total,
        state.version, updated.version,
    )


def snapshot(state: Ledger) -> dict[str, Any]:
    if type(state) is not Ledger:
        raise TypeError("invalid-ledger")
    return {
        "schema": SCHEMA, "market_id": MARKET_ID, "domain": DOMAIN,
        "commodity": COMMODITY, "stock": state.stock,
        "treasury": state.treasury, "holdings": state.holdings,
        "wallet": state.wallet, "capacity": CAPACITY,
        "tick": state.tick, "version": state.version,
        "buy_unit_price": quote("buy", 1, state),
        "sell_unit_price": quote("sell", 1, state),
        "receipt_count": len(state.receipts),
    }


def replay(
    commands: list[dict[str, Any]], initial: Ledger | None = None
) -> tuple[Ledger, tuple[ExchangeReceipt, ...]]:
    if type(commands) is not list or len(commands) > MAX_RECEIPTS:
        raise ValueError("invalid-batch")
    state = Ledger() if initial is None else initial
    receipts: list[ExchangeReceipt] = []
    for command in commands:
        state, receipt = transact(state, command)
        receipts.append(receipt)
    return state, tuple(receipts)
