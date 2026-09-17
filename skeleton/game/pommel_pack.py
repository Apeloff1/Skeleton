"""Named pommels."""

from __future__ import annotations

from typing import Any


class PommelPackError(ValueError):
    pass


POMMEL = tuple(f"pm_{i:02d}" for i in range(8))


def set_pommel(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in POMMEL:
        raise PommelPackError(name)
    nxt = dict(state)
    nxt["pommel"] = name
    nxt["stored_prose"] = 0
    return nxt
