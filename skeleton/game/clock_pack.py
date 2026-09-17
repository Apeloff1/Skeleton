"""Named clock phases."""

from __future__ import annotations

from typing import Any


class ClockPackError(ValueError):
    pass


PHASE = tuple(f"ph_{i:02d}" for i in range(16))


def enter(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PHASE:
        raise ClockPackError(name)
    nxt = dict(state)
    nxt["phase"] = name
    nxt["heat"] = max(0, min(16, int(nxt.get("heat", 0)) + ((PHASE.index(name) % 5) - 2)))
    nxt["stored_prose"] = 0
    return nxt
