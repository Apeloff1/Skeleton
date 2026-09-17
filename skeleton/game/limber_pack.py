"""Named limber holes."""

from __future__ import annotations

from typing import Any


class LimberPackError(ValueError):
    pass


LIMBER = tuple(f"lm_{i:02d}" for i in range(12))


def drain(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in LIMBER:
        raise LimberPackError(name)
    nxt = dict(node)
    nxt["limber"] = name
    nxt["water"] = max(0, int(nxt.get("water", 0)) - 1)
    nxt["stored_prose"] = 0
    return nxt
