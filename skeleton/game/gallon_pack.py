"""Named gallons."""

from __future__ import annotations

from typing import Any


class GallonPackError(ValueError):
    pass


GALLON = tuple(f"gl_{i:02d}" for i in range(12))


def fill(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in GALLON:
        raise GallonPackError(name)
    nxt = dict(state)
    nxt["gallon"] = name
    nxt["gal"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
