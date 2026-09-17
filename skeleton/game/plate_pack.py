"""Named plates."""

from __future__ import annotations

from typing import Any


class PlatePackError(ValueError):
    pass


PLATE = tuple(f"pl_{i:02d}" for i in range(28))


def set_plate(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PLATE:
        raise PlatePackError(name)
    nxt = dict(node)
    have = list(nxt.get("plate") or [])
    if name not in have:
        have.append(name)
    nxt["plate"] = have
    nxt["stored_prose"] = 0
    return nxt
