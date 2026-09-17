"""Named oil pots."""

from __future__ import annotations

from typing import Any


class OilpotPackError(ValueError):
    pass


OIL = tuple(f"op_{i:02d}" for i in range(12))


def fill(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in OIL:
        raise OilpotPackError(name)
    nxt = dict(state)
    nxt["oilpot"] = name
    nxt["oil"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
