"""Named stallage fees."""

from __future__ import annotations

from typing import Any


class StallagePackError(ValueError):
    pass


FEE = tuple(f"sf_{i:02d}" for i in range(8))


def levy(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in FEE:
        raise StallagePackError(name)
    nxt = dict(state)
    nxt["stallage"] = name
    nxt["fee"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
