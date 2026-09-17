"""Named pitches."""

from __future__ import annotations

from typing import Any


class PitchPackError(ValueError):
    pass


PITCH = tuple(f"pi_{i:02d}" for i in range(16))


def set_pitch(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PITCH:
        raise PitchPackError(name)
    nxt = dict(node)
    nxt["pitch"] = name
    nxt["stored_prose"] = 0
    return nxt
