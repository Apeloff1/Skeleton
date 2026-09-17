"""Named reefs."""

from __future__ import annotations

from typing import Any


class ReefPackError(ValueError):
    pass


REEF = tuple(f"rf_{i:02d}" for i in range(12))


def take(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in REEF:
        raise ReefPackError(name)
    nxt = dict(state)
    nxt["reef"] = name
    nxt["area"] = max(0, int(nxt.get("area", 8)) - 1)
    nxt["stored_prose"] = 0
    return nxt
