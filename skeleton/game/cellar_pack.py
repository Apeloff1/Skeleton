"""Named cellar bins."""

from __future__ import annotations

from typing import Any


class CellarPackError(ValueError):
    pass


CELLAR = tuple(f"cl_{i:02d}" for i in range(16))


def stow(state: dict[str, Any], name: str, item: str) -> dict[str, Any]:
    if name not in CELLAR:
        raise CellarPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("cellar") or {})
    cell = list(cur.get(name) or [])
    cell.append(item)
    cur[name] = cell
    nxt["cellar"] = cur
    nxt["stored_prose"] = 0
    return nxt
