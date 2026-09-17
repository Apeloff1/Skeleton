"""Named grain bins."""

from __future__ import annotations

from typing import Any


class GrainbinPackError(ValueError):
    pass


BIN = tuple(f"gb_{i:02d}" for i in range(12))


def fill(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in BIN:
        raise GrainbinPackError(name)
    nxt = dict(state)
    nxt["grainbin"] = name
    nxt["grain"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
