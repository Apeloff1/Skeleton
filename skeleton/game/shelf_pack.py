"""Named shelves."""

from __future__ import annotations

from typing import Any


class ShelfPackError(ValueError):
    pass


SHELF = tuple(f"sh_{i:02d}" for i in range(24))


def put(state: dict[str, Any], name: str, folio: str) -> dict[str, Any]:
    if name not in SHELF:
        raise ShelfPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("shelf") or {})
    cell = list(cur.get(name) or [])
    cell.append(folio)
    cur[name] = cell
    nxt["shelf"] = cur
    nxt["stored_prose"] = 0
    return nxt
