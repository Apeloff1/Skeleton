"""Named pounce."""

from __future__ import annotations

from typing import Any


class PouncePackError(ValueError):
    pass


POUNCE = tuple(f"pn_{i:02d}" for i in range(8))


def dust(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in POUNCE:
        raise PouncePackError(name)
    nxt = dict(state)
    nxt["pounce"] = name
    nxt["dry"] = 1
    nxt["stored_prose"] = 0
    return nxt
