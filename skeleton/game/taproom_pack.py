"""Named taprooms."""

from __future__ import annotations

from typing import Any


class TaproomPackError(ValueError):
    pass


TAP = tuple(f"tp_{i:02d}" for i in range(8))


def set_tap(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TAP:
        raise TaproomPackError(name)
    nxt = dict(node)
    nxt["taproom"] = name
    nxt["stored_prose"] = 0
    return nxt
