"""Named rennet lots."""

from __future__ import annotations

from typing import Any


class RennetPackError(ValueError):
    pass


RENNET = tuple(f"rn_{i:02d}" for i in range(8))


def add(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in RENNET:
        raise RennetPackError(name)
    nxt = dict(state)
    nxt["rennet"] = name
    nxt["set"] = 1
    nxt["stored_prose"] = 0
    return nxt
