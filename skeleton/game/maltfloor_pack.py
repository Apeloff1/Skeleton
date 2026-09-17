"""Named malt floors."""

from __future__ import annotations

from typing import Any


class MaltfloorPackError(ValueError):
    pass


FLOOR = tuple(f"mf_{i:02d}" for i in range(8))


def turn(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FLOOR:
        raise MaltfloorPackError(name)
    nxt = dict(node)
    nxt["maltfloor"] = name
    nxt["turn"] = int(nxt.get("turn", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
