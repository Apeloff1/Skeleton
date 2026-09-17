"""Named journeymen."""

from __future__ import annotations

from typing import Any


class JourneymanPackError(ValueError):
    pass


JOURNEY = tuple(f"jy_{i:02d}" for i in range(12))


def set_journey(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in JOURNEY:
        raise JourneymanPackError(name)
    nxt = dict(state)
    nxt["journeyman"] = name
    nxt["stored_prose"] = 0
    return nxt
