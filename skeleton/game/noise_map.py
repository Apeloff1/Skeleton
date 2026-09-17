"""Named noise sources."""

from __future__ import annotations

from typing import Any


class NoiseMapError(ValueError):
    pass


SRC = tuple(f"nz_{i:02d}" for i in range(24))


def emit(node: dict[str, Any], name: str, t: int) -> dict[str, Any]:
    if name not in SRC:
        raise NoiseMapError(name)
    nxt = dict(node)
    nxt["noise"] = name
    nxt["loud"] = min(16, int(nxt.get("loud", 0)) + 1 + (SRC.index(name) % 3) + (t % 2))
    nxt["stored_prose"] = 0
    return nxt
