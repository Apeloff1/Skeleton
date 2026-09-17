"""Named touchstones."""

from __future__ import annotations

from typing import Any


class TouchstonePackError(ValueError):
    pass


TOUCH = tuple(f"ts_{i:02d}" for i in range(8))


def streak(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TOUCH:
        raise TouchstonePackError(name)
    nxt = dict(state)
    nxt["touchstone"] = name
    nxt["streak"] = 1
    nxt["stored_prose"] = 0
    return nxt
