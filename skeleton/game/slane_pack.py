"""Named slanes."""

from __future__ import annotations

from typing import Any


class SlanePackError(ValueError):
    pass


SLANE = tuple(f"sl_{i:02d}" for i in range(8))


def set_slane(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SLANE:
        raise SlanePackError(name)
    nxt = dict(state)
    nxt["slane"] = name
    nxt["stored_prose"] = 0
    return nxt
