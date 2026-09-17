"""Named corner pieces."""

from __future__ import annotations

from typing import Any


class CornerpiecePackError(ValueError):
    pass


CORNER = tuple(f"cp_{i:02d}" for i in range(8))


def set_corner(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CORNER:
        raise CornerpiecePackError(name)
    nxt = dict(state)
    have = list(nxt.get("cornerpiece") or [])
    have.append(name)
    nxt["cornerpiece"] = have
    nxt["stored_prose"] = 0
    return nxt
