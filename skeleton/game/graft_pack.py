"""Named grafts."""

from __future__ import annotations

from typing import Any


class GraftPackError(ValueError):
    pass


GRAFT = tuple(f"gf_{i:02d}" for i in range(12))


def join(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in GRAFT:
        raise GraftPackError(name)
    nxt = dict(state)
    nxt["graft"] = name
    nxt["take"] = 1
    nxt["stored_prose"] = 0
    return nxt
