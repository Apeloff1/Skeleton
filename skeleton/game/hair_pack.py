"""Named hair lots for mortar."""

from __future__ import annotations

from typing import Any


class HairPackError(ValueError):
    pass


HAIR = tuple(f"hr_{i:02d}" for i in range(12))


def bind(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HAIR:
        raise HairPackError(name)
    nxt = dict(state)
    nxt["hair"] = name
    nxt["stored_prose"] = 0
    return nxt
