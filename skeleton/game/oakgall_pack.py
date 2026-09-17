"""Named oak galls."""

from __future__ import annotations

from typing import Any


class OakgallPackError(ValueError):
    pass


GALL = tuple(f"og_{i:02d}" for i in range(12))


def crush(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in GALL:
        raise OakgallPackError(name)
    nxt = dict(state)
    nxt["oakgall"] = name
    nxt["ink"] = int(nxt.get("ink", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
