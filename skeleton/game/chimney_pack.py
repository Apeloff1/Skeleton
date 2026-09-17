"""Named chimneys."""

from __future__ import annotations

from typing import Any


class ChimneyPackError(ValueError):
    pass


CHIMNEY = tuple(f"ch_{i:02d}" for i in range(12))


def set_chimney(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CHIMNEY:
        raise ChimneyPackError(name)
    nxt = dict(node)
    nxt["chimney"] = name
    nxt["stored_prose"] = 0
    return nxt
