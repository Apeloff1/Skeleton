"""Named hand leads."""

from __future__ import annotations

from typing import Any


class HandleadPackError(ValueError):
    pass


HAND = tuple(f"hd_{i:02d}" for i in range(8))


def heave(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HAND:
        raise HandleadPackError(name)
    nxt = dict(state)
    nxt["handlead"] = name
    nxt["cast"] = int(nxt.get("cast", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
