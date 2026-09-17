"""Named steelyards."""

from __future__ import annotations

from typing import Any


class SteelyardPackError(ValueError):
    pass


STEEL = tuple(f"sy_{i:02d}" for i in range(8))


def set_yard(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STEEL:
        raise SteelyardPackError(name)
    nxt = dict(state)
    nxt["steelyard"] = name
    nxt["stored_prose"] = 0
    return nxt
