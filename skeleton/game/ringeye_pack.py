"""Named ring eyes."""

from __future__ import annotations

from typing import Any


class RingeyePackError(ValueError):
    pass


RING = tuple(f"re_{i:02d}" for i in range(8))


def set_ring(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in RING:
        raise RingeyePackError(name)
    nxt = dict(state)
    nxt["ringeye"] = name
    nxt["stored_prose"] = 0
    return nxt
