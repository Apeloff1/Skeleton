"""Named mordants."""

from __future__ import annotations

from typing import Any


class MordantPackError(ValueError):
    pass


MORDANT = tuple(f"md_{i:02d}" for i in range(12))


def set_mordant(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in MORDANT:
        raise MordantPackError(name)
    nxt = dict(state)
    nxt["mordant"] = name
    nxt["stored_prose"] = 0
    return nxt
