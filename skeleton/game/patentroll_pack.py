"""Named patent rolls."""

from __future__ import annotations

from typing import Any


class PatentrollPackError(ValueError):
    pass


PATENT = tuple(f"pt_{i:02d}" for i in range(12))


def enter(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PATENT:
        raise PatentrollPackError(name)
    nxt = dict(state)
    nxt["patentroll"] = name
    nxt["open"] = 1
    nxt["stored_prose"] = 0
    return nxt
