"""Named charters."""

from __future__ import annotations

from typing import Any


class CharterPackError(ValueError):
    pass


CHARTER = tuple(f"ch_{i:02d}" for i in range(8))


def grant(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CHARTER:
        raise CharterPackError(name)
    nxt = dict(state)
    nxt["charter"] = name
    nxt["granted"] = 1
    nxt["stored_prose"] = 0
    return nxt
