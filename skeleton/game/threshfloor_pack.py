"""Named threshing floors."""

from __future__ import annotations

from typing import Any


class ThreshfloorPackError(ValueError):
    pass


FLOOR = tuple(f"tf_{i:02d}" for i in range(8))


def set_floor(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FLOOR:
        raise ThreshfloorPackError(name)
    nxt = dict(node)
    nxt["threshfloor"] = name
    nxt["stored_prose"] = 0
    return nxt
