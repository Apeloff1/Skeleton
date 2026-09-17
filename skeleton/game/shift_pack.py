"""Named work shifts."""

from __future__ import annotations

from typing import Any


class ShiftPackError(ValueError):
    pass


SHIFTS = tuple(f"sf_{i:02d}" for i in range(20))


def start(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SHIFTS:
        raise ShiftPackError(name)
    nxt = dict(state)
    nxt["shift"] = name
    nxt["tokens"] = int(nxt.get("tokens", 8)) + 1
    nxt["stored_prose"] = 0
    return nxt


def end(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SHIFTS:
        raise ShiftPackError(name)
    nxt = dict(state)
    if nxt.get("shift") == name:
        nxt["shift"] = ""
        nxt["xp"] = int(nxt.get("xp", 0)) + 1 + (SHIFTS.index(name) % 2)
    nxt["stored_prose"] = 0
    return nxt
