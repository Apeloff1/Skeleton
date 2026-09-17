"""Named dibbles."""

from __future__ import annotations

from typing import Any


class DibblePackError(ValueError):
    pass


DIBBLE = tuple(f"db_{i:02d}" for i in range(12))


def poke(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in DIBBLE:
        raise DibblePackError(name)
    nxt = dict(state)
    nxt["dibble"] = name
    nxt["hole"] = int(nxt.get("hole", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
