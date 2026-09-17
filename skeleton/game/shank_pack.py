"""Named shanks."""

from __future__ import annotations

from typing import Any


class ShankPackError(ValueError):
    pass


SHANK = tuple(f"sh_{i:02d}" for i in range(8))


def set_shank(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SHANK:
        raise ShankPackError(name)
    nxt = dict(state)
    nxt["shank"] = name
    nxt["stored_prose"] = 0
    return nxt
