"""Named stooks."""

from __future__ import annotations

from typing import Any


class StookPackError(ValueError):
    pass


STOOK = tuple(f"st_{i:02d}" for i in range(16))


def stack(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STOOK:
        raise StookPackError(name)
    nxt = dict(state)
    have = list(nxt.get("stook") or [])
    have.append(name)
    nxt["stook"] = have
    nxt["stored_prose"] = 0
    return nxt
