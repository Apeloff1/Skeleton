"""Named bushels."""

from __future__ import annotations

from typing import Any


class BushelPackError(ValueError):
    pass


BUSHEL = tuple(f"bu_{i:02d}" for i in range(12))


def fill(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in BUSHEL:
        raise BushelPackError(name)
    nxt = dict(state)
    nxt["bushel"] = name
    nxt["bu"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
