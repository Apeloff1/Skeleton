"""Named diet beats."""

from __future__ import annotations

from typing import Any


class DietPackError(ValueError):
    pass


DIET = tuple(f"dt_{i:02d}" for i in range(20))


def eat(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in DIET:
        raise DietPackError(name)
    nxt = dict(state)
    if int(nxt.get("scrap", 0)) < 1:
        raise DietPackError("food")
    nxt["scrap"] = int(nxt.get("scrap", 0)) - 1
    nxt["hp"] = min(40, int(nxt.get("hp", 40)) + 1 + (DIET.index(name) % 3))
    nxt["diet"] = name
    nxt["stored_prose"] = 0
    return nxt
