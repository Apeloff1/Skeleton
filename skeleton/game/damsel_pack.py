"""Named damsels."""

from __future__ import annotations

from typing import Any


class DamselPackError(ValueError):
    pass


DAMSEL = tuple(f"dm_{i:02d}" for i in range(8))


def tap(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in DAMSEL:
        raise DamselPackError(name)
    nxt = dict(state)
    nxt["damsel"] = name
    nxt["tap"] = int(nxt.get("tap", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
