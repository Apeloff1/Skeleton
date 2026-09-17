"""Named loads."""

from __future__ import annotations

from typing import Any


class LoadPackError(ValueError):
    pass


LOAD = tuple(f"ld_{i:02d}" for i in range(28))


def set_load(node: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in LOAD:
        raise LoadPackError(name)
    nxt = dict(node)
    cur = dict(nxt.get("load") or {})
    cur[name] = max(0, int(n))
    nxt["load"] = cur
    nxt["stored_prose"] = 0
    return nxt
