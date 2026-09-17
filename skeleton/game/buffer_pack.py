"""Named buffers."""

from __future__ import annotations

from typing import Any


class BufferPackError(ValueError):
    pass


BUFFER = tuple(f"bf_{i:02d}" for i in range(20))


def hit(state: dict[str, Any], name: str, force: int) -> dict[str, Any]:
    if name not in BUFFER:
        raise BufferPackError(name)
    nxt = dict(state)
    nxt["buffer"] = name
    nxt["shock"] = max(0, int(force) - 2)
    nxt["stored_prose"] = 0
    return nxt
