"""Named smokers."""

from __future__ import annotations

from typing import Any


class SmokerPackError(ValueError):
    pass


SMOKER = tuple(f"sm_{i:02d}" for i in range(8))


def puff(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SMOKER:
        raise SmokerPackError(name)
    nxt = dict(state)
    nxt["smoker"] = name
    nxt["calm"] = 1
    nxt["stored_prose"] = 0
    return nxt
