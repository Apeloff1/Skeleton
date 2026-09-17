"""Named valves."""

from __future__ import annotations

from typing import Any


class ValvePackError(ValueError):
    pass


VALVE = tuple(f"vv_{i:02d}" for i in range(20))


def open_valve(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in VALVE:
        raise ValvePackError(name)
    nxt = dict(node)
    nxt["valve"] = name
    nxt["open"] = True
    nxt["stored_prose"] = 0
    return nxt
