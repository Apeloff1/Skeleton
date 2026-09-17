"""Named oyster rakes."""

from __future__ import annotations

from typing import Any


class OysterrakePackError(ValueError):
    pass


RAKE = tuple(f"or_{i:02d}" for i in range(8))


def rake(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in RAKE:
        raise OysterrakePackError(name)
    nxt = dict(state)
    nxt["oysterrake"] = name
    nxt["take"] = int(nxt.get("take", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
