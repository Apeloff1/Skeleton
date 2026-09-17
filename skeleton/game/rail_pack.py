"""Named rails."""

from __future__ import annotations

from typing import Any


class RailPackError(ValueError):
    pass


RAIL = tuple(f"rl_{i:02d}" for i in range(28))


def lay(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in RAIL:
        raise RailPackError(name)
    nxt = dict(node)
    have = list(nxt.get("rail") or [])
    if name not in have:
        have.append(name)
    nxt["rail"] = have
    nxt["stored_prose"] = 0
    return nxt
