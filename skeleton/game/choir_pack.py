"""Named choir voices."""

from __future__ import annotations

from typing import Any


class ChoirPackError(ValueError):
    pass


VOICES = tuple(f"chv_{i:02d}" for i in range(20))


def sing(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in VOICES:
        raise ChoirPackError(name)
    nxt = dict(state)
    nxt["voice"] = name
    nxt["alert"] = int(nxt.get("alert", 0)) + (VOICES.index(name) % 3)
    nxt["stored_prose"] = 0
    return nxt
