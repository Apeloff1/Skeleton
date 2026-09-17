"""Named charcoal lots."""

from __future__ import annotations

from typing import Any


class CharPackError(ValueError):
    pass


CHAR = tuple(f"ch_{i:02d}" for i in range(24))


def burn(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CHAR:
        raise CharPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("char") or {})
    if int(cur.get(name, 0)) < 1:
        raise CharPackError("empty")
    cur[name] = int(cur.get(name, 0)) - 1
    nxt["char"] = cur
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 2)
    nxt["stored_prose"] = 0
    return nxt


def load(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CHAR:
        raise CharPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("char") or {})
    cur[name] = int(cur.get(name, 0)) + 1
    nxt["char"] = cur
    nxt["stored_prose"] = 0
    return nxt
