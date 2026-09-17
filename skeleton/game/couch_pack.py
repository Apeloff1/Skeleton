"""Named couches."""

from __future__ import annotations

from typing import Any


class CouchPackError(ValueError):
    pass


COUCH = tuple(f"ch_{i:02d}" for i in range(12))


def turn(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in COUCH:
        raise CouchPackError(name)
    nxt = dict(state)
    nxt["couch"] = name
    nxt["sheet"] = int(nxt.get("sheet", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
