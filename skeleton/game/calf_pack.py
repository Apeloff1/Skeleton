"""Named calf covers."""

from __future__ import annotations

from typing import Any


class CalfPackError(ValueError):
    pass


CALF = tuple(f"cf_{i:02d}" for i in range(8))


def cover(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CALF:
        raise CalfPackError(name)
    nxt = dict(state)
    nxt["calf"] = name
    nxt["stored_prose"] = 0
    return nxt
