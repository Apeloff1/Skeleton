"""Named glazes."""

from __future__ import annotations

from typing import Any


class GlazePackError(ValueError):
    pass


GLAZE = tuple(f"gz_{i:02d}" for i in range(20))


def dip(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in GLAZE:
        raise GlazePackError(name)
    nxt = dict(state)
    nxt["glaze"] = name
    nxt["stored_prose"] = 0
    return nxt
