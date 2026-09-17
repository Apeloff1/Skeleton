"""Named vendors. Stock + offer. No coin."""

from __future__ import annotations

from typing import Any


class VendorPackError(ValueError):
    pass


VENDORS = tuple(f"ven_{i:02d}" for i in range(16))


def buy(state: dict[str, Any], name: str, slot: str) -> dict[str, Any]:
    if name not in VENDORS:
        raise VendorPackError(name)
    nxt = dict(state)
    stock = dict(nxt.get("stock") or {})
    if int(stock.get(slot, 0)) < 1:
        raise VendorPackError("stock")
    if int(nxt.get("xp", 0)) < 2:
        raise VendorPackError("xp")
    stock[slot] = int(stock.get(slot, 0)) - 1
    nxt[slot] = int(nxt.get(slot, 0)) + 1
    nxt["xp"] = int(nxt.get("xp", 0)) - 2
    nxt["stock"] = stock
    nxt["vendor"] = name
    nxt["stored_prose"] = 0
    return nxt
