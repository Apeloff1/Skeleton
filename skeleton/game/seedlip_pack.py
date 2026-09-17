"""Named seedlips."""

from __future__ import annotations

from typing import Any


class SeedlipPackError(ValueError):
    pass


LIP = tuple(f"sl_{i:02d}" for i in range(8))


def fill(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in LIP:
        raise SeedlipPackError(name)
    nxt = dict(state)
    nxt["seedlip"] = name
    nxt["seed"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
