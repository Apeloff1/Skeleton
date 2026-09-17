"""Named longlines."""

from __future__ import annotations

from typing import Any


class LonglinePackError(ValueError):
    pass


LINE = tuple(f"ll_{i:02d}" for i in range(12))


def set_line(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in LINE:
        raise LonglinePackError(name)
    nxt = dict(state)
    nxt["longline"] = name
    nxt["hooks"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
