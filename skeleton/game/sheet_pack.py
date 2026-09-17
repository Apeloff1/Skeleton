"""Named map sheets. Pointer only."""

from __future__ import annotations

from typing import Any


class SheetPackError(ValueError):
    pass


SHEET = tuple(f"sh_{i:02d}" for i in range(24))


def add(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SHEET:
        raise SheetPackError(name)
    nxt = dict(state)
    have = list(nxt.get("sheet") or [])
    if name not in have:
        have.append(name)
    nxt["sheet"] = have
    nxt["stored_prose"] = 0
    return nxt
