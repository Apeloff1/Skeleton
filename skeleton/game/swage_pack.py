"""Named swages."""

from __future__ import annotations

from typing import Any


class SwagePackError(ValueError):
    pass


SWAGE = tuple(f"sw_{i:02d}" for i in range(12))


def form(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SWAGE:
        raise SwagePackError(name)
    nxt = dict(state)
    nxt["swage"] = name
    nxt["stored_prose"] = 0
    return nxt
