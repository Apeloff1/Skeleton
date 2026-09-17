"""Named tallow lots."""

from __future__ import annotations

from typing import Any


class TallowPackError(ValueError):
    pass


TALLOW = tuple(f"tl_{i:02d}" for i in range(12))


def render(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TALLOW:
        raise TallowPackError(name)
    nxt = dict(state)
    nxt["tallow"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 1)
    nxt["stored_prose"] = 0
    return nxt
