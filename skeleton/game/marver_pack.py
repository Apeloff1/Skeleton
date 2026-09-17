"""Named marvers."""

from __future__ import annotations

from typing import Any


class MarverPackError(ValueError):
    pass


MARVER = tuple(f"mv_{i:02d}" for i in range(8))


def roll(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in MARVER:
        raise MarverPackError(name)
    nxt = dict(state)
    nxt["marver"] = name
    nxt["stored_prose"] = 0
    return nxt
