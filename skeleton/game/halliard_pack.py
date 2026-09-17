"""Named halliards."""

from __future__ import annotations

from typing import Any


class HalliardPackError(ValueError):
    pass


HALLIARD = tuple(f"ha_{i:02d}" for i in range(12))


def haul(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HALLIARD:
        raise HalliardPackError(name)
    nxt = dict(state)
    nxt["halliard"] = name
    nxt["up"] = 1
    nxt["stored_prose"] = 0
    return nxt
