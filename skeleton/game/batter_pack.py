"""Named batters."""

from __future__ import annotations

from typing import Any


class BatterPackError(ValueError):
    pass


BATTER = tuple(f"bt_{i:02d}" for i in range(8))


def set_batter(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in BATTER:
        raise BatterPackError(name)
    nxt = dict(state)
    nxt["batter"] = name
    nxt["slope"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
