"""Named grindstones."""

from __future__ import annotations

from typing import Any


class GrindPackError(ValueError):
    pass


GRIND = tuple(f"gs_{i:02d}" for i in range(16))


def spin(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in GRIND:
        raise GrindPackError(name)
    nxt = dict(state)
    nxt["grind"] = name
    nxt["xp"] = int(nxt.get("xp", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
