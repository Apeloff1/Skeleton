"""Named smokehouses."""

from __future__ import annotations

from typing import Any


class SmokehousePackError(ValueError):
    pass


HOUSE = tuple(f"sh_{i:02d}" for i in range(8))


def set_house(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HOUSE:
        raise SmokehousePackError(name)
    nxt = dict(node)
    nxt["smokehouse"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 1)
    nxt["stored_prose"] = 0
    return nxt
