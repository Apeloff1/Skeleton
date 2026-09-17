"""Named draw hitches."""

from __future__ import annotations

from typing import Any


class DrawhitPackError(ValueError):
    pass


HIT = tuple(f"dh_{i:02d}" for i in range(8))


def hitch(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HIT:
        raise DrawhitPackError(name)
    nxt = dict(state)
    nxt["drawhit"] = name
    nxt["hitched"] = 1
    nxt["stored_prose"] = 0
    return nxt
