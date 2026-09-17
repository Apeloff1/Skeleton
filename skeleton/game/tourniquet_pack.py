"""Named tourniquets."""

from __future__ import annotations

from typing import Any


class TourniquetPackError(ValueError):
    pass


TQ = tuple(f"tq_{i:02d}" for i in range(12))


def bind(state: dict[str, Any], name: str, site: str) -> dict[str, Any]:
    if name not in TQ:
        raise TourniquetPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("tq") or {})
    cur[name] = site
    nxt["tq"] = cur
    nxt["stored_prose"] = 0
    return nxt
