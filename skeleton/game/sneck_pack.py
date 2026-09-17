"""Named snecks."""

from __future__ import annotations

from typing import Any


class SneckPackError(ValueError):
    pass


SNECK = tuple(f"sn_{i:02d}" for i in range(8))


def latch(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SNECK:
        raise SneckPackError(name)
    nxt = dict(state)
    nxt["sneck"] = name
    nxt["latched"] = 1
    nxt["stored_prose"] = 0
    return nxt
