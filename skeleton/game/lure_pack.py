"""Named lures."""

from __future__ import annotations

from typing import Any


class LurePackError(ValueError):
    pass


LURES = tuple(f"lu_{i:02d}" for i in range(16))


def drop(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in LURES:
        raise LurePackError(name)
    nxt = dict(node)
    nxt["lure"] = name
    nxt["alert"] = int(nxt.get("alert", 0)) + (LURES.index(name) % 3)
    nxt["stored_prose"] = 0
    return nxt
