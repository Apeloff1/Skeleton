"""Named tile nibs."""

from __future__ import annotations

from typing import Any


class NibPackError(ValueError):
    pass


NIB = tuple(f"nb_{i:02d}" for i in range(16))


def hang(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in NIB:
        raise NibPackError(name)
    nxt = dict(node)
    nxt["nib"] = name
    nxt["tile"] = int(nxt.get("tile", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
