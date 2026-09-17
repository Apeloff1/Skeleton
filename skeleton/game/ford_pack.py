"""Named fords."""

from __future__ import annotations

from typing import Any


class FordPackError(ValueError):
    pass


FORD = tuple(f"fd_{i:02d}" for i in range(8))


def set_ford(node: dict[str, Any], name: str, depth: int) -> dict[str, Any]:
    if name not in FORD:
        raise FordPackError(name)
    nxt = dict(node)
    nxt["ford"] = name
    nxt["depth"] = max(0, int(depth))
    nxt["stored_prose"] = 0
    return nxt
