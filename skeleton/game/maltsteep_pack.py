"""Named malt steeps."""

from __future__ import annotations

from typing import Any


class MaltsteepPackError(ValueError):
    pass


STEEP = tuple(f"mt_{i:02d}" for i in range(8))


def soak(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STEEP:
        raise MaltsteepPackError(name)
    nxt = dict(state)
    nxt["maltsteep"] = name
    nxt["wet"] = int(nxt.get("wet", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
