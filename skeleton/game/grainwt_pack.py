"""Named grain weights."""

from __future__ import annotations

from typing import Any


class GrainwtPackError(ValueError):
    pass


GRAIN = tuple(f"gn_{i:02d}" for i in range(12))


def weigh(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in GRAIN:
        raise GrainwtPackError(name)
    nxt = dict(state)
    nxt["grainwt"] = name
    nxt["gr"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
