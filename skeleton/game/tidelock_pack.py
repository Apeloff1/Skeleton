"""Named tide locks."""

from __future__ import annotations

from typing import Any


class TidelockPackError(ValueError):
    pass


TLOCK = tuple(f"tl_{i:02d}" for i in range(12))


def cycle(node: dict[str, Any], name: str, level: int) -> dict[str, Any]:
    if name not in TLOCK:
        raise TidelockPackError(name)
    nxt = dict(node)
    nxt["tidelock"] = name
    nxt["open"] = int(level) >= 4
    nxt["stored_prose"] = 0
    return nxt
