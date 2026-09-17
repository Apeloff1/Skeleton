"""Named bolt ropes."""

from __future__ import annotations

from typing import Any


class BoltropePackError(ValueError):
    pass


BOLTROPE = tuple(f"br_{i:02d}" for i in range(12))


def sew(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BOLTROPE:
        raise BoltropePackError(name)
    nxt = dict(state)
    nxt["boltrope"] = name
    nxt["stored_prose"] = 0
    return nxt
