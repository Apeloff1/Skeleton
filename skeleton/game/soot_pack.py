"""Named soot falls."""

from __future__ import annotations

from typing import Any


class SootPackError(ValueError):
    pass


SOOT = tuple(f"so_{i:02d}" for i in range(20))


def fall(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SOOT:
        raise SootPackError(name)
    nxt = dict(node)
    nxt["soot"] = name
    nxt["los_pen"] = min(8, int(nxt.get("los_pen", 0)) + 1)
    nxt["stored_prose"] = 0
    return nxt
