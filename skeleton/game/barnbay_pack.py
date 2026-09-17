"""Named barn bays."""

from __future__ import annotations

from typing import Any


class BarnbayPackError(ValueError):
    pass


BAY = tuple(f"bb_{i:02d}" for i in range(8))


def set_bay(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BAY:
        raise BarnbayPackError(name)
    nxt = dict(node)
    nxt["barnbay"] = name
    nxt["stored_prose"] = 0
    return nxt
