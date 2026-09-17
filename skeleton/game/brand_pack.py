"""Named brands on items."""

from __future__ import annotations

from typing import Any


class BrandPackError(ValueError):
    pass


BRAND = tuple(f"br_{i:02d}" for i in range(24))


def stamp(state: dict[str, Any], name: str, slot: str) -> dict[str, Any]:
    if name not in BRAND:
        raise BrandPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("brand") or {})
    cur[slot] = name
    nxt["brand"] = cur
    nxt["stored_prose"] = 0
    return nxt
