"""Named pawls."""

from __future__ import annotations

from typing import Any


class PawlPackError(ValueError):
    pass


PAWL = tuple(f"pw_{i:02d}" for i in range(12))


def lock(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PAWL:
        raise PawlPackError(name)
    nxt = dict(state)
    nxt["pawl"] = name
    nxt["locked"] = 1
    nxt["stored_prose"] = 0
    return nxt
