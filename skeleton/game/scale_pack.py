"""Named oxide scale."""

from __future__ import annotations

from typing import Any


class ScalePackError(ValueError):
    pass


SCALE = tuple(f"sc_{i:02d}" for i in range(20))


def form(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SCALE:
        raise ScalePackError(name)
    nxt = dict(node)
    nxt["scale"] = int(nxt.get("scale", 0)) + 1 + (SCALE.index(name) % 2)
    nxt["stored_prose"] = 0
    return nxt
