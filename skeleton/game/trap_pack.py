"""Named traps."""

from __future__ import annotations

from typing import Any


class TrapPackError(ValueError):
    pass


TRAPS = tuple(f"tr_{i:02d}" for i in range(20))


def arm(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TRAPS:
        raise TrapPackError(name)
    nxt = dict(node)
    nxt["trap"] = name
    nxt["armed"] = 1
    nxt["stored_prose"] = 0
    return nxt


def trip(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TRAPS:
        raise TrapPackError(name)
    nxt = dict(state)
    nxt["hp"] = max(0, int(nxt.get("hp", 40)) - (1 + (TRAPS.index(name) % 3)))
    nxt["stored_prose"] = 0
    return nxt
