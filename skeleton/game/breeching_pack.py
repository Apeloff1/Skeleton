"""Named breechings."""

from __future__ import annotations

from typing import Any


class BreechingPackError(ValueError):
    pass


BREECH = tuple(f"br_{i:02d}" for i in range(8))


def set_breech(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BREECH:
        raise BreechingPackError(name)
    nxt = dict(state)
    nxt["breeching"] = name
    nxt["stored_prose"] = 0
    return nxt
