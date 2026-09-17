"""Named pitch lots."""

from __future__ import annotations

from typing import Any


class PitchlotPackError(ValueError):
    pass


PITCH = tuple(f"ph_{i:02d}" for i in range(12))


def heat(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PITCH:
        raise PitchlotPackError(name)
    nxt = dict(state)
    nxt["pitchlot"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 2)
    nxt["stored_prose"] = 0
    return nxt
