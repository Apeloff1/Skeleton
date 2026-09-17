"""Named compass bearings."""

from __future__ import annotations

from typing import Any


class CompassPackError(ValueError):
    pass


BEAR = tuple(f"cp_{i:02d}" for i in range(24))


def set_bearing(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BEAR:
        raise CompassPackError(name)
    nxt = dict(state)
    nxt["bearing"] = name
    nxt["stored_prose"] = 0
    return nxt
