"""Named chimneys."""

from __future__ import annotations

from typing import Any


class ChimneyPackError(ValueError):
    pass


CHIM = tuple(f"cy_{i:02d}" for i in range(16))


def vent(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CHIM:
        raise ChimneyPackError(name)
    nxt = dict(node)
    nxt["chimney"] = name
    nxt["los_pen"] = min(8, int(nxt.get("los_pen", 0)) + 1)
    nxt["stored_prose"] = 0
    return nxt
