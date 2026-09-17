"""Named cords of wood."""

from __future__ import annotations

from typing import Any


class CordPackError(ValueError):
    pass


CORD = tuple(f"cd_{i:02d}" for i in range(12))


def measure(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CORD:
        raise CordPackError(name)
    nxt = dict(state)
    nxt["cord"] = name
    nxt["wood"] = int(nxt.get("wood", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
