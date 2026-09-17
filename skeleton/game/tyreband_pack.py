"""Named tyre bands."""

from __future__ import annotations

from typing import Any


class TyrebandPackError(ValueError):
    pass


TYRE = tuple(f"ty_{i:02d}" for i in range(8))


def shrink(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TYRE:
        raise TyrebandPackError(name)
    nxt = dict(state)
    nxt["tyreband"] = name
    nxt["tight"] = 1
    nxt["stored_prose"] = 0
    return nxt
