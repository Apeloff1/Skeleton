"""Named reaches."""

from __future__ import annotations

from typing import Any


class ReachPackError(ValueError):
    pass


REACH = tuple(f"rc_{i:02d}" for i in range(8))


def set_reach(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in REACH:
        raise ReachPackError(name)
    nxt = dict(state)
    nxt["reach"] = name
    nxt["len"] = max(1, int(n))
    nxt["stored_prose"] = 0
    return nxt
