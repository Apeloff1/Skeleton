"""Named temperature bands."""

from __future__ import annotations

from typing import Any


class TempPackError(ValueError):
    pass


BAND = tuple(f"tp_{i:02d}" for i in range(20))


def tick(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BAND:
        raise TempPackError(name)
    nxt = dict(node)
    nxt["band"] = name
    nxt["heat"] = max(0, min(16, BAND.index(name)))
    nxt["stored_prose"] = 0
    return nxt
