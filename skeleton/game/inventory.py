"""Inventory + equipment slots. Barter only. N-cap stacks."""

from __future__ import annotations

from typing import Any


SLOTS = ("bag", "hand", "key", "bait", "coil")
MAX_STACK = 16


class InventoryError(ValueError):
    pass


def empty() -> dict[str, int]:
    return {slot: 0 for slot in SLOTS}


def add(inv: dict[str, int], slot: str, n: int = 1) -> dict[str, int]:
    if slot not in SLOTS:
        raise InventoryError("slot")
    nxt = dict(inv)
    nxt[slot] = int(nxt.get(slot, 0)) + int(n)
    if nxt[slot] < 0 or nxt[slot] > MAX_STACK:
        raise InventoryError("stack")
    nxt["stored_prose"] = 0  # type: ignore[assignment]
    return nxt


def take(inv: dict[str, int], slot: str, n: int = 1) -> dict[str, int]:
    if int(inv.get(slot, 0)) < n:
        raise InventoryError("missing")
    return add(inv, slot, -n)


def card(inv: dict[str, int]) -> dict[str, Any]:
    return {"kind": "inventory", "slots": {k: int(inv.get(k, 0)) for k in SLOTS}, "stored_prose": 0}
