"""Named stays."""

from __future__ import annotations

from typing import Any


class StaylinePackError(ValueError):
    pass


STAY = tuple(f"st_{i:02d}" for i in range(12))


def set_stay(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STAY:
        raise StaylinePackError(name)
    nxt = dict(node)
    nxt["stay"] = name
    nxt["stored_prose"] = 0
    return nxt
