"""Named bilges."""

from __future__ import annotations

from typing import Any


class BilgePackError(ValueError):
    pass


BILGE = tuple(f"bg_{i:02d}" for i in range(8))


def set_bilge(node: dict[str, Any], name: str, water: int) -> dict[str, Any]:
    if name not in BILGE:
        raise BilgePackError(name)
    nxt = dict(node)
    nxt["bilge"] = name
    nxt["water"] = max(0, int(water))
    nxt["stored_prose"] = 0
    return nxt
