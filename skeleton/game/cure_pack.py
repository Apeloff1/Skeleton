"""Named cures."""

from __future__ import annotations

from typing import Any


class CurePackError(ValueError):
    pass


CURE = tuple(f"cu_{i:02d}" for i in range(12))


def set_cure(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CURE:
        raise CurePackError(name)
    nxt = dict(state)
    nxt["cure"] = name
    nxt["days"] = int(nxt.get("days", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
