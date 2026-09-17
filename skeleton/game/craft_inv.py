"""Craft against inventory slots. Barter-only. Fail-closed."""

from __future__ import annotations

from typing import Any

from skeleton.game.inventory import add, empty, take


class CraftInvError(ValueError):
    pass


RECIPES = {
    "coil": (("scrap", 2), ("parts", 1), "coil"),
    "bait": (("scrap", 1), ("parts", 0), "bait"),
    "key": (("parts", 2), ("coil", 0), "key"),
}


def craft(inv: dict[str, int], name: str) -> dict[str, int]:
    if name not in RECIPES:
        raise CraftInvError(name)
    (src_a, na), (src_b, nb), dst = RECIPES[name]
    bag = dict(inv) if inv else empty()
    if na:
        bag = take(bag, src_a, na)
    if nb:
        bag = take(bag, src_b, nb)
    bag = add(bag, dst, 1)
    return bag


def kit(seed: int) -> dict[str, Any]:
    bag = empty()
    bag = add(bag, "scrap", 4)
    bag = add(bag, "parts", 2)
    bag = craft(bag, "coil")
    bag = craft(bag, "bait")
    try:
        bag = craft(bag, "key")
    except CraftInvError:
        pass
    return {
        "kind": "craft_kit",
        "seed": int(seed),
        "slots": {k: int(bag.get(k, 0)) for k in ("bag", "hand", "key", "bait", "coil")},
        "stored_prose": 0,
    }
