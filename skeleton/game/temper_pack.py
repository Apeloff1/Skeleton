"""Named tempers."""

from __future__ import annotations

from typing import Any


class TemperPackError(ValueError):
    pass


TEMPER = tuple(f"tm_{i:02d}" for i in range(16))


def set_temper(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TEMPER:
        raise TemperPackError(name)
    nxt = dict(state)
    nxt["temper"] = name
    nxt["heat"] = 4 + (TEMPER.index(name) % 8)
    nxt["stored_prose"] = 0
    return nxt
