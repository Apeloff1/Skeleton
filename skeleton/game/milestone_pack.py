"""Named milestones."""

from __future__ import annotations

from typing import Any


class MilestonePackError(ValueError):
    pass


MILE = tuple(f"ml_{i:02d}" for i in range(16))


def set_mile(node: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in MILE:
        raise MilestonePackError(name)
    nxt = dict(node)
    nxt["milestone"] = name
    nxt["mi"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
