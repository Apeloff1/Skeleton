"""Named morocco covers."""

from __future__ import annotations

from typing import Any


class MoroccoPackError(ValueError):
    pass


MOROCCO = tuple(f"mo_{i:02d}" for i in range(8))


def cover(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in MOROCCO:
        raise MoroccoPackError(name)
    nxt = dict(state)
    nxt["morocco"] = name
    nxt["stored_prose"] = 0
    return nxt
