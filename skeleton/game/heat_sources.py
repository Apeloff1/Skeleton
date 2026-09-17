"""Named heat sources."""

from __future__ import annotations

from typing import Any


class HeatSourceError(ValueError):
    pass


SRC = {f"src_{i:02d}": 1 + (i % 4) for i in range(32)}


def emit(name: str, node: dict[str, Any]) -> dict[str, Any]:
    if name not in SRC:
        raise HeatSourceError(name)
    nxt = dict(node)
    nxt["src"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + SRC[name])
    nxt["stored_prose"] = 0
    return nxt


def sink(name: str, node: dict[str, Any]) -> dict[str, Any]:
    if name not in SRC:
        raise HeatSourceError(name)
    nxt = dict(node)
    nxt["heat"] = max(0, int(nxt.get("heat", 0)) - SRC[name])
    nxt["stored_prose"] = 0
    return nxt
