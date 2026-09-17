"""Named latches."""

from __future__ import annotations

from typing import Any


class LatchPackError(ValueError):
    pass


LATCH = tuple(f"lc_{i:02d}" for i in range(20))


def set_latch(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in LATCH:
        raise LatchPackError(name)
    nxt = dict(node)
    nxt["latch"] = name
    nxt["latched"] = 1
    nxt["stored_prose"] = 0
    return nxt
