"""Named key bits."""

from __future__ import annotations

from typing import Any


class LockbitPackError(ValueError):
    pass


BIT = tuple(f"lb_{i:02d}" for i in range(12))


def set_bit(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BIT:
        raise LockbitPackError(name)
    nxt = dict(state)
    nxt["lockbit"] = name
    nxt["stored_prose"] = 0
    return nxt
