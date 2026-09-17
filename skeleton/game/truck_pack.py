"""Named trucks."""

from __future__ import annotations

from typing import Any


class TruckPackError(ValueError):
    pass


TRUCK = tuple(f"tr_{i:02d}" for i in range(8))


def set_truck(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TRUCK:
        raise TruckPackError(name)
    nxt = dict(node)
    nxt["truck"] = name
    nxt["stored_prose"] = 0
    return nxt
