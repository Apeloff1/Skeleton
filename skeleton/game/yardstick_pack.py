"""Named yardsticks."""

from __future__ import annotations

from typing import Any


class YardstickPackError(ValueError):
    pass


YARD = tuple(f"yd_{i:02d}" for i in range(8))


def measure(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in YARD:
        raise YardstickPackError(name)
    nxt = dict(state)
    nxt["yardstick"] = name
    nxt["yd"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
