"""Named stones."""

from __future__ import annotations

from typing import Any


class StonewtPackError(ValueError):
    pass


STONE = tuple(f"st_{i:02d}" for i in range(12))


def weigh(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in STONE:
        raise StonewtPackError(name)
    nxt = dict(state)
    nxt["stonewt"] = name
    nxt["st"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
