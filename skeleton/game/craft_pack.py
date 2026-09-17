"""Named craft recipes against inventory + state."""

from __future__ import annotations

from typing import Any

from skeleton.game.inventory import add, empty, take


class CraftPackError(ValueError):
    pass


RECIPES: dict[str, tuple[tuple[tuple[str, int], ...], str, int]] = {
    "coil": ((("scrap", 2), ("parts", 1)), "coil", 1),
    "bait": ((("scrap", 1),), "bait", 1),
    "key": ((("parts", 2),), "key", 1),
    "ward": ((("coil", 1), ("scrap", 1)), "heat", -3),
    "patch": ((("scrap", 1), ("parts", 1)), "hp", 4),
    "torch": ((("scrap", 1),), "heat", 2),
    "blanket": ((("scrap", 2),), "sleep", 3),
    "lure": ((("bait", 1), ("scrap", 1)), "alert", -2),
}


def craft(name: str, inv: dict[str, int], state: dict[str, Any]) -> tuple[dict[str, int], dict[str, Any]]:
    if name not in RECIPES:
        raise CraftPackError(name)
    need, dst, n = RECIPES[name]
    bag = dict(inv) if inv else empty()
    nxt = dict(state)
    for slot, qty in need:
        bag = take(bag, slot, qty)
    if dst in ("coil", "bait", "key"):
        bag = add(bag, dst, n)
    else:
        nxt[dst] = max(0, int(nxt.get(dst, 0)) + n)
    nxt["stored_prose"] = 0
    return bag, nxt
