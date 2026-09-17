"""Named chimes."""

from __future__ import annotations

from typing import Any


class ChimePackError(ValueError):
    pass


CHIME = tuple(f"cm_{i:02d}" for i in range(12))


def set_chime(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CHIME:
        raise ChimePackError(name)
    nxt = dict(state)
    nxt["chime"] = name
    nxt["stored_prose"] = 0
    return nxt
