"""Named scratch coats."""

from __future__ import annotations

from typing import Any


class ScratchPackError(ValueError):
    pass


SCRATCH = tuple(f"sc_{i:02d}" for i in range(12))


def key(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SCRATCH:
        raise ScratchPackError(name)
    nxt = dict(node)
    nxt["scratch"] = name
    nxt["coat"] = int(nxt.get("coat", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
