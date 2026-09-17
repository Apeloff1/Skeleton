"""Named fore-edges."""

from __future__ import annotations

from typing import Any


class ForedgePackError(ValueError):
    pass


EDGE = tuple(f"fe_{i:02d}" for i in range(8))


def paint(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in EDGE:
        raise ForedgePackError(name)
    nxt = dict(state)
    nxt["foredge"] = name
    nxt["gilt"] = 1
    nxt["stored_prose"] = 0
    return nxt
