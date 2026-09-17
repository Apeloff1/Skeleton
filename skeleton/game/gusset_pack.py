"""Named gussets."""

from __future__ import annotations

from typing import Any


class GussetPackError(ValueError):
    pass


GUSSET = tuple(f"gs_{i:02d}" for i in range(20))


def fit(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in GUSSET:
        raise GussetPackError(name)
    nxt = dict(node)
    nxt["gusset"] = name
    nxt["stress"] = max(0, int(nxt.get("stress", 0)) - 1)
    nxt["stored_prose"] = 0
    return nxt
