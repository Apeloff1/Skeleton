"""Named windlasses."""

from __future__ import annotations

from typing import Any


class WindlassPackError(ValueError):
    pass


WINDLASS = tuple(f"wd_{i:02d}" for i in range(8))


def crank(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in WINDLASS:
        raise WindlassPackError(name)
    nxt = dict(state)
    nxt["windlass"] = name
    nxt["rode"] = int(nxt.get("rode", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
