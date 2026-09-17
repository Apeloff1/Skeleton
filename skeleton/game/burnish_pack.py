"""Named burnishers."""

from __future__ import annotations

from typing import Any


class BurnishPackError(ValueError):
    pass


BURN = tuple(f"bn_{i:02d}" for i in range(8))


def rub(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BURN:
        raise BurnishPackError(name)
    nxt = dict(state)
    nxt["burnish"] = name
    nxt["shine"] = 1
    nxt["stored_prose"] = 0
    return nxt
