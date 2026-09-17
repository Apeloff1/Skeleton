"""Named canes."""

from __future__ import annotations

from typing import Any


class CanePackError(ValueError):
    pass


CANE = tuple(f"cn_{i:02d}" for i in range(16))


def prune(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CANE:
        raise CanePackError(name)
    nxt = dict(state)
    have = list(nxt.get("cane") or [])
    have.append(name)
    nxt["cane"] = have
    nxt["stored_prose"] = 0
    return nxt
