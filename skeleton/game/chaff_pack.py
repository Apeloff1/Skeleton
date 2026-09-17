"""Named chaff lots."""

from __future__ import annotations

from typing import Any


class ChaffPackError(ValueError):
    pass


CHAFF = tuple(f"cf_{i:02d}" for i in range(12))


def blow(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CHAFF:
        raise ChaffPackError(name)
    nxt = dict(state)
    nxt["chaff"] = name
    nxt["light"] = int(nxt.get("light", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
