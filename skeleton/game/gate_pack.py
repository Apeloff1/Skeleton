"""Named extract gates. Once only."""

from __future__ import annotations

from typing import Any


class GatePackError(ValueError):
    pass


GATES = tuple(f"gt_{i:02d}" for i in range(12))


def open_gate(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in GATES:
        raise GatePackError(name)
    nxt = dict(state)
    if int(nxt.get("heat", 0)) < 8:
        raise GatePackError("cold")
    if int(nxt.get("extracted", 0)) != 0:
        raise GatePackError("twice")
    nxt["gate"] = name
    nxt["extracted"] = 1
    nxt["warp_count"] = 1
    nxt["stored_prose"] = 0
    return nxt
