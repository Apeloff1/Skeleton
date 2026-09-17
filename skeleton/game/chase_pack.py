"""Named chases."""

from __future__ import annotations

from typing import Any


class ChasePackError(ValueError):
    pass


CHASE = tuple(f"cs_{i:02d}" for i in range(12))


def lock(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CHASE:
        raise ChasePackError(name)
    nxt = dict(state)
    nxt["chase"] = name
    nxt["locked"] = 1
    nxt["stored_prose"] = 0
    return nxt
