"""Named slakes."""

from __future__ import annotations

from typing import Any


class SlakePackError(ValueError):
    pass


SLAKE = tuple(f"sk_{i:02d}" for i in range(12))


def slake(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SLAKE:
        raise SlakePackError(name)
    nxt = dict(state)
    nxt["slake"] = name
    nxt["wet"] = int(nxt.get("wet", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
