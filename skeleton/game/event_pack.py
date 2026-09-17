"""Named world events. Discrete."""

from __future__ import annotations

from typing import Any


class EventPackError(ValueError):
    pass


EVENTS = tuple(f"evt_{i:02d}" for i in range(40))
STATS = ("heat", "sleep", "alert", "hp", "xp", "scrap", "key", "coil")


def fire(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in EVENTS:
        raise EventPackError(name)
    i = EVENTS.index(name)
    nxt = dict(state)
    nxt["event"] = name
    nxt[STATS[i % 8]] = max(0, int(nxt.get(STATS[i % 8], 0)) + ((i % 5) - 2))
    nxt["stored_prose"] = 0
    return nxt
