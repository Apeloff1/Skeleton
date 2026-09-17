"""Named pipes."""

from __future__ import annotations

from typing import Any


class PipePackError(ValueError):
    pass


PIPE = tuple(f"pp_{i:02d}" for i in range(24))


def flow(node: dict[str, Any], name: str, t: int) -> dict[str, Any]:
    if name not in PIPE:
        raise PipePackError(name)
    nxt = dict(node)
    nxt["pipe"] = name
    nxt["heat"] = max(0, min(16, int(nxt.get("heat", 0)) + ((t + PIPE.index(name)) % 3) - 1))
    nxt["stored_prose"] = 0
    return nxt
