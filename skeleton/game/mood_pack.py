"""Named moods."""

from __future__ import annotations

from typing import Any


class MoodPackError(ValueError):
    pass


MOOD = tuple(f"md_{i:02d}" for i in range(24))


def set_mood(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in MOOD:
        raise MoodPackError(name)
    nxt = dict(state)
    nxt["mood"] = name
    nxt["alert"] = max(0, int(nxt.get("alert", 0)) + ((MOOD.index(name) % 5) - 2))
    nxt["stored_prose"] = 0
    return nxt
