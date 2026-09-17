"""Named footings."""

from __future__ import annotations

from typing import Any


class FootingPackError(ValueError):
    pass


FOOT = tuple(f"ft_{i:02d}" for i in range(8))


def set_foot(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FOOT:
        raise FootingPackError(name)
    nxt = dict(state)
    nxt["footing"] = name
    nxt["stored_prose"] = 0
    return nxt
