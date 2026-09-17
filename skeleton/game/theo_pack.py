"""Named theodolites."""

from __future__ import annotations

from typing import Any


class TheoPackError(ValueError):
    pass


THEO = tuple(f"th_{i:02d}" for i in range(8))


def sight(state: dict[str, Any], name: str, az: int) -> dict[str, Any]:
    if name not in THEO:
        raise TheoPackError(name)
    nxt = dict(state)
    nxt["theo"] = name
    nxt["az"] = int(az) % 360
    nxt["stored_prose"] = 0
    return nxt
