"""Named ration books."""

from __future__ import annotations

from typing import Any


class RationPackError(ValueError):
    pass


BOOK = tuple(f"rb_{i:02d}" for i in range(16))


def stamp(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BOOK:
        raise RationPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("ration") or {})
    left = int(cur.get(name, 3 + (BOOK.index(name) % 3)))
    if left < 1:
        raise RationPackError("empty")
    cur[name] = left - 1
    nxt["ration"] = cur
    nxt["hp"] = min(40, int(nxt.get("hp", 40)) + 1)
    nxt["stored_prose"] = 0
    return nxt
