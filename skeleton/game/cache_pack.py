"""Named caches."""

from __future__ import annotations

from typing import Any


class CachePackError(ValueError):
    pass


CACHE = tuple(f"cc_{i:02d}" for i in range(20))


def hide(state: dict[str, Any], name: str, slot: str, n: int = 1) -> dict[str, Any]:
    if name not in CACHE:
        raise CachePackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("cache") or {})
    cell = dict(cur.get(name) or {})
    cell[slot] = int(cell.get(slot, 0)) + int(n)
    cur[name] = cell
    nxt["cache"] = cur
    nxt["stored_prose"] = 0
    return nxt
