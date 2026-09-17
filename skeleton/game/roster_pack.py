"""Named roster lines."""

from __future__ import annotations

from typing import Any


class RosterPackError(ValueError):
    pass


ROSTER = tuple(f"rs_{i:02d}" for i in range(24))


def add(state: dict[str, Any], name: str, who: str) -> dict[str, Any]:
    if name not in ROSTER:
        raise RosterPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("roster") or {})
    cur[name] = who
    nxt["roster"] = cur
    nxt["stored_prose"] = 0
    return nxt
