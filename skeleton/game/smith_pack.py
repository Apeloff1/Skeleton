"""Named smith marks."""

from __future__ import annotations

from typing import Any


class SmithMarkError(ValueError):
    pass


MARK = tuple(f"sm_{i:02d}" for i in range(28))


def stamp(state: dict[str, Any], name: str, slot: str) -> dict[str, Any]:
    if name not in MARK:
        raise SmithMarkError(name)
    nxt = dict(state)
    cur = dict(nxt.get("smith") or {})
    cur[slot] = name
    nxt["smith"] = cur
    nxt["stored_prose"] = 0
    return nxt
