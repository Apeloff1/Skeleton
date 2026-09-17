"""Named brick frogs."""

from __future__ import annotations

from typing import Any


class FrogPackError(ValueError):
    pass


FROG = tuple(f"fr_{i:02d}" for i in range(12))


def stamp(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FROG:
        raise FrogPackError(name)
    nxt = dict(state)
    nxt["frog"] = name
    nxt["stored_prose"] = 0
    return nxt
