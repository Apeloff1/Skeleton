"""Named pumps."""

from __future__ import annotations

from typing import Any


class PumpPackError(ValueError):
    pass


PUMP = tuple(f"pm_{i:02d}" for i in range(12))


def stroke(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PUMP:
        raise PumpPackError(name)
    nxt = dict(state)
    nxt["pump"] = name
    nxt["water"] = int(nxt.get("water", 0)) + 2
    nxt["stored_prose"] = 0
    return nxt
