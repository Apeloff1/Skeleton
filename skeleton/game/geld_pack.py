"""Named gelds."""

from __future__ import annotations

from typing import Any


class GeldPackError(ValueError):
    pass


GELD = tuple(f"gd_{i:02d}" for i in range(8))


def levy(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in GELD:
        raise GeldPackError(name)
    nxt = dict(state)
    nxt["geld"] = name
    nxt["due"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
