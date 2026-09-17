"""Named fireboxes."""

from __future__ import annotations

from typing import Any


class FireboxPackError(ValueError):
    pass


BOX = tuple(f"fb_{i:02d}" for i in range(16))


def stoke(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BOX:
        raise FireboxPackError(name)
    nxt = dict(node)
    nxt["box"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 2)
    nxt["stored_prose"] = 0
    return nxt
