"""Named swaths."""

from __future__ import annotations

from typing import Any


class SwathPackError(ValueError):
    pass


SWATH = tuple(f"sw_{i:02d}" for i in range(16))


def lay(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SWATH:
        raise SwathPackError(name)
    nxt = dict(state)
    have = list(nxt.get("swath") or [])
    have.append(name)
    nxt["swath"] = have
    nxt["stored_prose"] = 0
    return nxt
