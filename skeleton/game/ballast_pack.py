"""Named ballast lots."""

from __future__ import annotations

from typing import Any


class BallastPackError(ValueError):
    pass


BALLAST = tuple(f"bl_{i:02d}" for i in range(20))


def load(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BALLAST:
        raise BallastPackError(name)
    nxt = dict(state)
    have = list(nxt.get("ballast") or [])
    have.append(name)
    nxt["ballast"] = have
    nxt["mass"] = int(nxt.get("mass", 0)) + 1 + (BALLAST.index(name) % 3)
    nxt["stored_prose"] = 0
    return nxt
