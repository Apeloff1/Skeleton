"""Named abutments."""

from __future__ import annotations

from typing import Any


class AbutmentPackError(ValueError):
    pass


ABUT = tuple(f"ab_{i:02d}" for i in range(12))


def set_abut(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in ABUT:
        raise AbutmentPackError(name)
    nxt = dict(node)
    nxt["abutment"] = name
    nxt["stored_prose"] = 0
    return nxt
