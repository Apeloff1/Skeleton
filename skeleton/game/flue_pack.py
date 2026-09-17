"""Named flues."""

from __future__ import annotations

from typing import Any


class FluePackError(ValueError):
    pass


FLUE = tuple(f"fl_{i:02d}" for i in range(20))


def draw(node: dict[str, Any], name: str, t: int) -> dict[str, Any]:
    if name not in FLUE:
        raise FluePackError(name)
    nxt = dict(node)
    nxt["flue"] = name
    nxt["heat"] = max(0, min(16, int(nxt.get("heat", 0)) + ((t + FLUE.index(name)) % 3) - 1))
    nxt["stored_prose"] = 0
    return nxt
