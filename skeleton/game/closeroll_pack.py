"""Named close rolls."""

from __future__ import annotations

from typing import Any


class CloserollPackError(ValueError):
    pass


CLOSE = tuple(f"cr_{i:02d}" for i in range(12))


def enter(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CLOSE:
        raise CloserollPackError(name)
    nxt = dict(state)
    nxt["closeroll"] = name
    nxt["closed"] = 1
    nxt["stored_prose"] = 0
    return nxt
