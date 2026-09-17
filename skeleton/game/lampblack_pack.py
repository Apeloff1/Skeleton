"""Named lampblack."""

from __future__ import annotations

from typing import Any


class LampblackPackError(ValueError):
    pass


BLACK = tuple(f"lb_{i:02d}" for i in range(8))


def mix(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BLACK:
        raise LampblackPackError(name)
    nxt = dict(state)
    nxt["lampblack"] = name
    nxt["ink"] = int(nxt.get("ink", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
