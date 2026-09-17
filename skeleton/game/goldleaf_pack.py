"""Named gold leaf."""

from __future__ import annotations

from typing import Any


class GoldleafPackError(ValueError):
    pass


LEAF = tuple(f"gl_{i:02d}" for i in range(12))


def lay(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in LEAF:
        raise GoldleafPackError(name)
    nxt = dict(state)
    nxt["goldleaf"] = name
    nxt["gilt"] = 1
    nxt["stored_prose"] = 0
    return nxt
