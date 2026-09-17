"""Named through stones."""

from __future__ import annotations

from typing import Any


class ThroughstonePackError(ValueError):
    pass


THRU = tuple(f"ts_{i:02d}" for i in range(16))


def set_thru(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in THRU:
        raise ThroughstonePackError(name)
    nxt = dict(state)
    have = list(nxt.get("throughstone") or [])
    have.append(name)
    nxt["throughstone"] = have
    nxt["stored_prose"] = 0
    return nxt
