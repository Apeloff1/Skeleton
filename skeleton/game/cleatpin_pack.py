"""Named cleat pins."""

from __future__ import annotations

from typing import Any


class CleatpinPackError(ValueError):
    pass


CLEAT = tuple(f"cl_{i:02d}" for i in range(12))


def belay(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CLEAT:
        raise CleatpinPackError(name)
    nxt = dict(state)
    nxt["cleatpin"] = name
    nxt["belay"] = 1
    nxt["stored_prose"] = 0
    return nxt
