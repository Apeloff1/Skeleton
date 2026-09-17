"""Named barrels."""

from __future__ import annotations

from typing import Any


class BarrelPackError(ValueError):
    pass


BARREL = tuple(f"bl_{i:02d}" for i in range(12))


def set_barrel(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BARREL:
        raise BarrelPackError(name)
    nxt = dict(state)
    nxt["barrel"] = name
    nxt["stored_prose"] = 0
    return nxt
