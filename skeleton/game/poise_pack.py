"""Named poises."""

from __future__ import annotations

from typing import Any


class PoisePackError(ValueError):
    pass


POISE = tuple(f"po_{i:02d}" for i in range(12))


def slide(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in POISE:
        raise PoisePackError(name)
    nxt = dict(state)
    nxt["poise"] = name
    nxt["arm"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
