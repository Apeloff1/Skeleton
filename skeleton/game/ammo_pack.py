"""Named ammo kinds."""

from __future__ import annotations

from typing import Any


class AmmoPackError(ValueError):
    pass


AMMO = (
    "slug", "dart", "spark", "ash", "fogcap", "coilpin", "baitshot", "sealwax",
    "warpchip", "clipnail", "meshbit", "keypin", "scrapshot", "partspin", "sleepdart", "wardshot",
)


def load(state: dict[str, Any], name: str, n: int = 1) -> dict[str, Any]:
    if name not in AMMO:
        raise AmmoPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("ammo") or {})
    cur[name] = int(cur.get(name, 0)) + int(n)
    nxt["ammo"] = cur
    nxt["stored_prose"] = 0
    return nxt


def fire(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in AMMO:
        raise AmmoPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("ammo") or {})
    if int(cur.get(name, 0)) < 1:
        raise AmmoPackError("empty")
    cur[name] = int(cur.get(name, 0)) - 1
    nxt["ammo"] = cur
    nxt["stored_prose"] = 0
    return nxt
