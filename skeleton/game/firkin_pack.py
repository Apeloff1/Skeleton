"""Named firkins."""

from __future__ import annotations

from typing import Any


class FirkinPackError(ValueError):
    pass


FIRKIN = tuple(f"fk_{i:02d}" for i in range(8))


def fill(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in FIRKIN:
        raise FirkinPackError(name)
    nxt = dict(state)
    nxt["firkin"] = name
    nxt["fk"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
