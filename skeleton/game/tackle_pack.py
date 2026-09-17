"""Named tackles."""

from __future__ import annotations

from typing import Any


class TacklePackError(ValueError):
    pass


TACKLE = tuple(f"tk_{i:02d}" for i in range(12))


def haul(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TACKLE:
        raise TacklePackError(name)
    nxt = dict(state)
    nxt["tackle"] = name
    nxt["load"] = int(nxt.get("load", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
