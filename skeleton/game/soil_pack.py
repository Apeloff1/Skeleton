"""Named soil lots."""

from __future__ import annotations

from typing import Any


class SoilPackError(ValueError):
    pass


SOIL = tuple(f"so_{i:02d}" for i in range(16))


def fill(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SOIL:
        raise SoilPackError(name)
    nxt = dict(state)
    have = list(nxt.get("soil") or [])
    have.append(name)
    nxt["soil"] = have
    nxt["stored_prose"] = 0
    return nxt
