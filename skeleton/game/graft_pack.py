"""Named grafts."""

from __future__ import annotations

from typing import Any


class GraftPackError(ValueError):
    pass


GRAFT = tuple(f"gf_{i:02d}" for i in range(16))


def set_graft(node: dict[str, Any], name: str, stock: str) -> dict[str, Any]:
    if name not in GRAFT:
        raise GraftPackError(name)
    nxt = dict(node)
    cur = dict(nxt.get("graft") or {})
    cur[name] = stock
    nxt["graft"] = cur
    nxt["stored_prose"] = 0
    return nxt
